import argparse
import json
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
    OUTPUT_DIR,
    PDD_FAV_GOODS_URL,
    PDD_FAV_MALL_URL,
    SCROLL_INTERVAL,
)
from utils import format_timestamp, get_mobile_context


class PddFavoritesExporter:
    def __init__(self, save_interval: int = AUTO_SAVE_INTERVAL, headless: bool = False):
        self.save_interval = save_interval
        self.headless = headless
        
        self.captured_fav_goods: List[Dict[str, Any]] = []
        self.captured_fav_malls: List[Dict[str, Any]] = []
        self.seen_goods_ids: Set[str] = set()
        self.seen_mall_ids: Set[str] = set()

        self.last_saved_goods_count = 0
        self.last_saved_malls_count = 0

        self.excel_file = OUTPUT_DIR / "pdd_favorites.xlsx"
        self.fav_goods_csv = OUTPUT_DIR / "pdd_fav_goods.csv"
        self.fav_malls_csv = OUTPUT_DIR / "pdd_fav_malls.csv"

    def _flush_to_disk(self, force: bool = False):
        goods_diff = len(self.captured_fav_goods) - self.last_saved_goods_count
        malls_diff = len(self.captured_fav_malls) - self.last_saved_malls_count

        if not force and goods_diff < self.save_interval and malls_diff < self.save_interval:
            return

        try:
            with pd.ExcelWriter(self.excel_file, engine="openpyxl") as writer:
                if self.captured_fav_goods:
                    df_goods = pd.DataFrame(self.captured_fav_goods)
                    df_goods.to_excel(writer, sheet_name="商品收藏", index=False)
                    df_goods.to_csv(self.fav_goods_csv, index=False, encoding="utf_8_sig")
                else:
                    pd.DataFrame([{"提示": "暂无收藏的商品"}]).to_excel(writer, sheet_name="商品收藏", index=False)

                if self.captured_fav_malls:
                    df_malls = pd.DataFrame(self.captured_fav_malls)
                    df_malls.to_excel(writer, sheet_name="店铺关注", index=False)
                    df_malls.to_csv(self.fav_malls_csv, index=False, encoding="utf_8_sig")
                else:
                    pd.DataFrame([{"提示": "暂无关注的店铺"}]).to_excel(writer, sheet_name="店铺关注", index=False)

            self.last_saved_goods_count = len(self.captured_fav_goods)
            self.last_saved_malls_count = len(self.captured_fav_malls)
        except Exception:
            pass

    def _extract_goods_from_json(self, data: Any):
        if not isinstance(data, dict):
            return

        candidates = []
        for key in ["goods_list", "goodsList", "fav_goods_list", "list", "items", "data"]:
            val = data.get(key)
            if isinstance(val, list):
                candidates.extend(val)
            elif isinstance(val, dict):
                self._extract_goods_from_json(val)

        new_added = False
        for item in candidates:
            if not isinstance(item, dict):
                continue
            goods_id = str(item.get("goods_id") or item.get("goodsId") or "")
            goods_name = str(item.get("goods_name") or item.get("goodsName") or item.get("title") or "")
            if goods_id and goods_id not in self.seen_goods_ids and goods_name:
                self.seen_goods_ids.add(goods_id)
                
                price_raw = item.get("price") or item.get("min_group_price") or item.get("group_price") or item.get("goods_price") or 0
                try:
                    price = round(float(price_raw) / 100, 2) if float(price_raw) > 100 and "." not in str(price_raw) else float(price_raw)
                except Exception:
                    price = price_raw

                is_on_sale = item.get("is_onsale", 1)
                is_sold_out = item.get("is_sold_out") or item.get("sold_out") or 0
                status_desc = str(item.get("status_desc") or item.get("status_name") or item.get("status_prompt") or "")
                
                if is_sold_out or "售罄" in status_desc or item.get("is_invalid") == 1:
                    goods_status = "已售罄"
                elif is_on_sale == 0 or "下架" in status_desc:
                    goods_status = "已下架"
                elif "失效" in status_desc:
                    goods_status = "已失效"
                elif status_desc:
                    goods_status = status_desc
                else:
                    goods_status = "在售"

                mall_info = item.get("mall") or {}
                mall_name = (
                    mall_info.get("mall_name")
                    or mall_info.get("mallName")
                    or item.get("mall_name")
                    or item.get("mallName")
                    or ""
                )

                self.captured_fav_goods.append({
                    "商品ID": goods_id,
                    "商品名称": goods_name,
                    "价格(元)": price,
                    "商品状态": goods_status,
                    "店铺名称": mall_name,
                    "优惠/成团信息": item.get("sales_tip") or item.get("salesTip") or item.get("side_sales_tip") or "",
                    "商品链接": f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}",
                })
                new_added = True

        if new_added:
            self._flush_to_disk(force=False)

    def _extract_malls_from_json(self, data: Any):
        if not isinstance(data, dict):
            return

        candidates = []
        for key in ["mall_list", "mallList", "fav_mall_list", "list", "items", "data"]:
            val = data.get(key)
            if isinstance(val, list):
                candidates.extend(val)
            elif isinstance(val, dict):
                self._extract_malls_from_json(val)

        new_added = False
        for item in candidates:
            if not isinstance(item, dict):
                continue
            mall_id = str(item.get("mall_id") or item.get("mallId") or "")
            mall_name = str(item.get("mall_name") or item.get("mallName") or "")
            if mall_id and mall_id not in self.seen_mall_ids and mall_name:
                self.seen_mall_ids.add(mall_id)
                self.captured_fav_malls.append({
                    "店铺ID": mall_id,
                    "店铺名称": mall_name,
                    "关注人数": item.get("fav_count") or item.get("favCount") or "",
                    "在售商品数": item.get("goods_num") or item.get("goodsNum") or "",
                    "店铺链接": f"https://mobile.yangkeduo.com/mall_page.html?mall_id={mall_id}",
                })
                new_added = True

        if new_added:
            self._flush_to_disk(force=False)

    def _extract_from_html_scripts(self, page, mode: str = "goods"):
        try:
            raw_data = page.evaluate("() => window.rawData || null")
            if raw_data:
                if mode == "goods":
                    self._extract_goods_from_json(raw_data)
                else:
                    self._extract_malls_from_json(raw_data)
        except Exception:
            pass

        try:
            html = page.content()
            if "window.rawData=" in html:
                idx = html.find("window.rawData=") + len("window.rawData=")
                end_idx = html.find("</script>", idx)
                json_str = html[idx:end_idx].strip().rstrip(";")
                d = json.loads(json_str)
                if mode == "goods":
                    self._extract_goods_from_json(d)
                else:
                    self._extract_malls_from_json(d)
        except Exception:
            pass

    def run(self):
        print("【拼多多买家收藏导出】")

        with sync_playwright() as playwright:
            context = get_mobile_context(playwright, headless=self.headless)
            page = context.pages[0] if context.pages else context.new_page()

            print(f"[*] 步骤 1/2: 正在打开【商品收藏】页面: {PDD_FAV_GOODS_URL}")
            
            def on_goods_response(response: Response):
                url = response.url.lower()
                if any(k in url for k in ["fav", "collect", "goods", "like", "recommendation"]):
                    try:
                        self._extract_goods_from_json(response.json())
                    except Exception:
                        pass

            page.on("response", on_goods_response)
            page.goto(PDD_FAV_GOODS_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            self._extract_from_html_scripts(page, mode="goods")

            idle_count = 0
            prev_goods_cnt = len(self.captured_fav_goods)
            scroll_r = 0
            while True:
                scroll_r += 1
                page.evaluate("window.scrollBy(0, window.innerHeight * 2);")
                page.mouse.wheel(0, 1500)
                time.sleep(SCROLL_INTERVAL)

                curr_cnt = len(self.captured_fav_goods)
                print(f"\r[*] 第 {scroll_r} 轮滑动中... 已捕获【商品收藏】: {curr_cnt} 件", end="", flush=True)

                if curr_cnt > prev_goods_cnt:
                    prev_goods_cnt = curr_cnt
                    idle_count = 0
                else:
                    idle_count += 1
                    page.keyboard.press("Space")
                    page.keyboard.press("PageDown")

                if idle_count >= 10:
                    print(f"\n[√] 【商品收藏】已全部加载完毕 (共 {curr_cnt} 件)！")
                    break

            self._flush_to_disk(force=True)

            print(f"[*] 步骤 2/2: 正在打开【店铺关注】页面: {PDD_FAV_MALL_URL}")
            
            page.remove_listener("response", on_goods_response)
            
            def on_mall_response(response: Response):
                url = response.url.lower()
                if any(k in url for k in ["mall", "fllw", "follow", "collection"]):
                    try:
                        self._extract_malls_from_json(response.json())
                    except Exception:
                        pass

            page.on("response", on_mall_response)
            page.goto(PDD_FAV_MALL_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            self._extract_from_html_scripts(page, mode="mall")

            idle_count = 0
            prev_mall_cnt = len(self.captured_fav_malls)
            scroll_r = 0
            while True:
                scroll_r += 1
                page.evaluate("window.scrollBy(0, window.innerHeight * 2);")
                page.mouse.wheel(0, 1500)
                time.sleep(SCROLL_INTERVAL)

                curr_cnt = len(self.captured_fav_malls)
                print(f"\r[*] 第 {scroll_r} 轮滑动中... 已捕获【店铺关注】: {curr_cnt} 家", end="", flush=True)

                if curr_cnt > prev_mall_cnt:
                    prev_mall_cnt = curr_cnt
                    idle_count = 0
                else:
                    idle_count += 1
                    page.keyboard.press("Space")
                    page.keyboard.press("PageDown")

                if idle_count >= 10:
                    print(f"\n[√] 【店铺关注】已全部加载完毕 (共 {curr_cnt} 家)！")
                    break

            self._flush_to_disk(force=True)
            context.close()

        print("【全部收藏与关注导出完成】")
        print(f"[*] 商品收藏共: {len(self.captured_fav_goods)} 件")
        print(f"[*] 店铺关注共: {len(self.captured_fav_malls)} 家")
        print(f"[√] Excel: {self.excel_file}")
        print(f"[√] 商品收藏 CSV:       {self.fav_goods_csv}")
        print(f"[√] 店铺关注 CSV:       {self.fav_malls_csv}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="拼多多买家收藏导出工具")
    parser.add_argument("--save-interval", type=int, default=AUTO_SAVE_INTERVAL, help="实时落盘保存间隔(默认10条)")
    parser.add_argument("--headless", action="store_true", help="是否无头模式运行")
    args = parser.parse_args()

    exporter = PddFavoritesExporter(save_interval=args.save_interval, headless=args.headless)
    exporter.run()
