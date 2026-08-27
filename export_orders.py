import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set
import pandas as pd
from playwright.sync_api import Response, sync_playwright

from config import (
    AUTH_FILE,
    AUTO_SAVE_INTERVAL,
    MAX_IDLE_SCROLLS,
    OUTPUT_DIR,
    PDD_ORDERS_URL,
    SCROLL_INTERVAL,
)
from utils import calculate_bought_statistics, get_mobile_context, parse_order_raw_item


class PddOrderExporter:
    def __init__(self, save_interval: int = AUTO_SAVE_INTERVAL, headless: bool = False):
        self.save_interval = save_interval
        self.headless = headless
        
        self.raw_queue: List[Dict[str, Any]] = []
        self.captured_raw_orders: List[Dict[str, Any]] = []
        self.seen_order_keys: Set[str] = set()
        self.all_parsed_records: List[Dict[str, Any]] = []
        
        self.last_saved_count = 0
        self.excel_path = OUTPUT_DIR / "pdd_orders.xlsx"
        self.csv_path = OUTPUT_DIR / "pdd_orders.csv"
        self.json_path = OUTPUT_DIR / "pdd_orders.json"

    def _flush_to_disk(self, force: bool = False):
        total_now = len(self.all_parsed_records)
        if total_now == 0:
            return

        if force or (total_now - self.last_saved_count >= self.save_interval):
            try:
                df = pd.DataFrame(self.all_parsed_records)
                df.to_excel(self.excel_path, index=False, engine="openpyxl")
                df.to_csv(self.csv_path, index=False, encoding="utf_8_sig")
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(self.all_parsed_records, f, ensure_ascii=False, indent=2)

                self.last_saved_count = total_now
            except Exception:
                pass

    def _drain_queue(self, force: bool = False):
        new_added = False
        while self.raw_queue:
            item = self.raw_queue.pop(0)
            order_sn = item.get("order_sn") or item.get("orderSn") or item.get("order_id") or ""
            
            records = parse_order_raw_item(item)
            for r in records:
                dedup_key = f"{r.get('订单编号')}_{r.get('商品名称')}_{r.get('商品规格')}"
                if dedup_key not in self.seen_order_keys:
                    self.seen_order_keys.add(dedup_key)
                    self.all_parsed_records.append(r)
                    new_added = True
            
            if order_sn and not any(o.get('order_sn') == order_sn or o.get('orderSn') == order_sn for o in self.captured_raw_orders):
                self.captured_raw_orders.append(item)

        if new_added or force:
            self._flush_to_disk(force=force)

    def _extract_orders_from_json(self, data: Any):
        if not isinstance(data, dict):
            return

        candidates = []
        if "orders" in data and isinstance(data["orders"], list):
            candidates.extend(data["orders"])
        if "order_list" in data and isinstance(data["order_list"], list):
            candidates.extend(data["order_list"])
        if "items" in data and isinstance(data["items"], list):
            candidates.extend(data["items"])
        if "data" in data:
            if isinstance(data["data"], list):
                candidates.extend(data["data"])
            elif isinstance(data["data"], dict):
                self._extract_orders_from_json(data["data"])
        if "result" in data and isinstance(data["result"], dict):
            self._extract_orders_from_json(data["result"])

        for c in candidates:
            if isinstance(c, dict):
                self.raw_queue.append(c)

    def _extract_orders_from_html_scripts(self, page):
        try:
            raw_data = page.evaluate("() => window.rawData || null")
            if raw_data and isinstance(raw_data, dict):
                store = raw_data.get("ordersStore", {})
                for key in ["orders", "itemsStore", "cachedOrder", "expressOrdersList", "initOdersList"]:
                    items = store.get(key)
                    if isinstance(items, list):
                        for o in items:
                            self.raw_queue.append(o)
                self._extract_orders_from_json(raw_data)
        except Exception:
            pass

        try:
            html = page.content()
            if "window.rawData=" in html:
                idx = html.find("window.rawData=") + len("window.rawData=")
                end_idx = html.find("</script>", idx)
                json_str = html[idx:end_idx].strip().rstrip(";")
                data = json.loads(json_str)
                store = data.get("ordersStore", {})
                for key in ["orders", "itemsStore", "cachedOrder", "expressOrdersList", "initOdersList"]:
                    items = store.get(key)
                    if isinstance(items, list):
                        for o in items:
                            self.raw_queue.append(o)
        except Exception:
            pass

    def _handle_response(self, response: Response):
        url = response.url.lower()
        if any(keyword in url for keyword in ["order", "aristotle", "mall"]):
            try:
                data = response.json()
                self._extract_orders_from_json(data)
            except Exception:
                pass

    def run(self):
        print("【拼多多买家订单导出】")

        with sync_playwright() as playwright:
            context = get_mobile_context(playwright, headless=self.headless)
            page = context.pages[0] if context.pages else context.new_page()

            page.on("response", self._handle_response)

            print(f"[*] 正在打开全部订单页面: {PDD_ORDERS_URL}")
            page.goto(PDD_ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            if "login.html" in page.url:
                print("[!] 登录凭证已失效，请先运行 python login.py 完成登录。")
                return

            self._extract_orders_from_html_scripts(page)
            self._drain_queue()
            
            print(f"[*] 首屏初始化完成，已提取最新订单 {len(self.all_parsed_records)} 条。开始自动滚动加载历史订单...")

            idle_scroll_count = 0
            prev_records_count = len(self.all_parsed_records)
            scroll_round = 0

            while True:
                scroll_round += 1
                
                page.evaluate("window.scrollBy(0, window.innerHeight * 2);")
                page.mouse.wheel(0, 1500)
                time.sleep(SCROLL_INTERVAL)

                self._drain_queue()

                current_records_count = len(self.all_parsed_records)
                oldest_time_str = ""
                if self.all_parsed_records:
                    all_times = [r.get("下单时间", "") for r in self.all_parsed_records if r.get("下单时间")]
                    if all_times:
                        oldest_time_str = f" | 已回溯至: {min(all_times)[:10]}"

                print(f"\r[*] 第 {scroll_round} 轮滑动中... 已捕获商品明细: {current_records_count} 条{oldest_time_str}", end="", flush=True)

                if current_records_count > prev_records_count:
                    prev_records_count = current_records_count
                    idle_scroll_count = 0
                else:
                    idle_scroll_count += 1
                    page.keyboard.press("Space")
                    page.keyboard.press("PageDown")
                    page.keyboard.press("End")

                is_end = page.evaluate("""() => {
                    const text = document.body ? document.body.innerText : "";
                    return text.includes("没有更多订单") || 
                           text.includes("已加载全部") || 
                           text.includes("没有更多了") ||
                           text.includes("已经到底了");
                }""")

                if idle_scroll_count >= MAX_IDLE_SCROLLS:
                    if is_end:
                        print(f"\n[√] 页面检测到已加载到历史最底部！")
                        break
                    else:
                        print(f"\n[*] 连续多轮无新订单加载，抓取完毕。")
                        break

            try:
                react_items = page.evaluate("""() => {
                    try {
                        if (window.itemsStore && Array.isArray(window.itemsStore)) {
                            return window.itemsStore;
                        }
                    } catch (e) {}
                    return [];
                }""")
                if react_items:
                    for it in react_items:
                        self.raw_queue.append(it)
                    self._drain_queue()
            except Exception:
                pass

            context.close()

        self._drain_queue(force=True)

        print("【全部订单导出完成】")
        print(f"[*] 累计捕获商品明细: {len(self.all_parsed_records)} 条")
        print(f"[√] Excel:   {self.excel_path}")
        print(f"[√] CSV:     {self.csv_path}")
        print(f"[√] JSON:    {self.json_path}")

        stats = calculate_bought_statistics(self.all_parsed_records)
        print("【已买到的商品消费统计】")
        print(f"[*] 商品数量: {stats['total_goods_quantity']} 件")
        print(f"[*] 实际成交订单笔数: {stats['total_orders_count']} 笔")
        print(f"[*] 实际消费总金额:   {stats['total_amount']:.2f} 元")
        for st, c in stats["status_counts"].items():
            print(f"    - {st}: {c['records']} 条明细, 共 {c['quantity']} 件")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="拼多多买家订单导出工具")
    parser.add_argument("--save-interval", type=int, default=AUTO_SAVE_INTERVAL, help="实时落盘保存间隔(默认10条)")
    parser.add_argument("--headless", action="store_true", help="是否无头模式运行")
    args = parser.parse_args()

    exporter = PddOrderExporter(save_interval=args.save_interval, headless=args.headless)
    exporter.run()
