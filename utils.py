import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from playwright.sync_api import BrowserContext, Playwright

from config import AUTH_FILE, BASE_DIR, MOBILE_USER_AGENT, MOBILE_VIEWPORT


def cleanup_profile_locks():
    profile_dir = BASE_DIR / "pdd_profile"
    if profile_dir.exists():
        for fname in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
            fpath = profile_dir / fname
            try:
                if fpath.exists():
                    fpath.unlink()
            except Exception:
                pass


def get_mobile_context(
    playwright: Playwright,
    headless: bool = False,
) -> BrowserContext:
    profile_dir = BASE_DIR / "pdd_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    cleanup_profile_locks()

    browser_context = None
    for ch in ["msedge", "chrome", None]:
        try:
            browser_context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=headless,
                channel=ch,
                viewport=MOBILE_VIEWPORT,
                user_agent=MOBILE_USER_AGENT,
                is_mobile=True,
                has_touch=True,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--window-position=300,100",
                    "--window-size=460,920",
                ],
            )
            break
        except Exception:
            continue

    if not browser_context:
        browser_context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport=MOBILE_VIEWPORT,
            user_agent=MOBILE_USER_AGENT,
            is_mobile=True,
            has_touch=True,
        )

    browser_context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    if AUTH_FILE.exists():
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                auth = json.load(f)
                if "cookies" in auth and auth["cookies"]:
                    browser_context.add_cookies(auth["cookies"])
        except Exception:
            pass

    return browser_context


def format_timestamp(ts: Any) -> str:
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            ts = int(ts[:10])
        elif isinstance(ts, (int, float)):
            if ts > 1e11:
                ts = ts / 1000
            ts = int(ts)
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def parse_order_raw_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    order_type = item.get("type", 1)
    order_sn = item.get("order_sn", "") or item.get("orderSn", "") or item.get("order_id", "")
    order_status = (
        item.get("order_status_prompt", "")
        or item.get("orderStatusPrompt", "")
        or item.get("status_prompt", "")
        or item.get("status_name", "")
    )
    
    mall_info = item.get("mall", {}) or {}
    mall_name = (
        mall_info.get("mall_name", "")
        or mall_info.get("mallName", "")
        or item.get("mall_name", "")
        or item.get("mallName", "")
    )

    order_goods_list = (
        item.get("order_goods")
        or item.get("orderGoods")
        or item.get("goods_list")
        or item.get("goodsList")
        or []
    )
    
    order_amount_raw = item.get("order_amount") or item.get("orderAmount") or item.get("display_amount") or item.get("displayAmount") or 0
    try:
        order_amount = (
            round(float(order_amount_raw) / 100, 2)
            if float(order_amount_raw) > 100 and "." not in str(order_amount_raw)
            else float(order_amount_raw)
        )
    except Exception:
        order_amount = order_amount_raw

    order_time_raw = (
        item.get("order_time")
        or item.get("orderTime")
        or item.get("created_at")
        or item.get("pay_time")
    )
    created_at = format_timestamp(order_time_raw)

    if order_type == 1 or order_goods_list:
        if not order_goods_list:
            goods_id = str(item.get("goods_id") or item.get("goodsId") or "")
            goods_name = str(item.get("goods_name") or item.get("goodsName") or item.get("title") or "")
            spec = str(item.get("spec") or item.get("goods_spec") or "")
            price_raw = item.get("goods_price") or item.get("goodsPrice") or order_amount
            try:
                goods_price = round(float(price_raw) / 100, 2) if float(price_raw) > 100 else float(price_raw)
            except Exception:
                goods_price = price_raw
            
            results.append({
                "订单编号": order_sn,
                "订单类型": "普通订单",
                "商品名称": goods_name,
                "商品规格": spec,
                "单价(元)": goods_price,
                "数量": item.get("goods_number") or item.get("goodsNumber") or 1,
                "订单总金额(元)": order_amount,
                "订单状态": order_status,
                "店铺名称": mall_name,
                "下单时间": created_at,
                "商品链接": f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}" if goods_id else "",
            })
        else:
            for g in order_goods_list:
                goods_id = str(g.get("goods_id") or g.get("goodsId") or "")
                goods_name = str(g.get("goods_name") or g.get("goodsName") or "")
                spec = str(g.get("spec") or g.get("goods_spec") or g.get("spec_name") or "")
                goods_price_raw = g.get("goods_price") or g.get("goodsPrice") or 0
                try:
                    goods_price = (
                        round(float(goods_price_raw) / 100, 2)
                        if float(goods_price_raw) > 100 and "." not in str(goods_price_raw)
                        else float(goods_price_raw)
                    )
                except Exception:
                    goods_price = goods_price_raw
                    
                goods_qty = g.get("goods_number") or g.get("goodsNumber") or g.get("quantity") or 1
                buy_url = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}" if goods_id else ""

                results.append({
                    "订单编号": order_sn,
                    "订单类型": "普通订单",
                    "商品名称": goods_name,
                    "商品规格": spec,
                    "单价(元)": goods_price,
                    "数量": goods_qty,
                    "订单总金额(元)": order_amount,
                    "订单状态": order_status,
                    "店铺名称": mall_name,
                    "下单时间": created_at,
                    "商品链接": buy_url,
                })

    elif order_type == 2 or "orders" in item:
        sub_orders = item.get("orders", []) or []
        sort_id = str(item.get("sort_id") or item.get("sortId") or "")
        created_at = format_timestamp(sort_id[:10]) if sort_id else created_at

        for sub_o in sub_orders:
            sub_goods_list = sub_o.get("order_goods") or sub_o.get("orderGoods") or []
            for g in sub_goods_list:
                goods_id = str(g.get("goods_id") or g.get("goodsId") or "")
                goods_name = str(g.get("goods_name") or g.get("goodsName") or "")
                spec = str(g.get("spec") or g.get("goods_spec") or "")
                goods_price_raw = g.get("goods_price") or g.get("goodsPrice") or 0
                try:
                    goods_price = round(float(goods_price_raw) / 100, 2) if float(goods_price_raw) > 100 else float(goods_price_raw)
                except Exception:
                    goods_price = goods_price_raw
                goods_qty = g.get("goods_number") or g.get("goodsNumber") or 1
                buy_url = f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}" if goods_id else "多多买菜门店商品"

                results.append({
                    "订单编号": order_sn,
                    "订单类型": "多多买菜",
                    "商品名称": goods_name,
                    "商品规格": spec,
                    "单价(元)": goods_price,
                    "数量": goods_qty,
                    "订单总金额(元)": order_amount,
                    "订单状态": order_status,
                    "店铺名称": "多多买菜",
                    "下单时间": created_at,
                    "商品链接": buy_url,
                })
    else:
        results.append({
            "订单编号": order_sn,
            "订单类型": f"其他类型({order_type})",
            "商品名称": str(item.get("goods_name") or item.get("goodsName") or item.get("title") or ""),
            "商品规格": str(item.get("spec") or item.get("goods_spec") or ""),
            "单价(元)": "",
            "数量": 1,
            "订单总金额(元)": order_amount,
            "订单状态": order_status,
            "店铺名称": mall_name,
            "下单时间": created_at,
            "商品链接": "",
        })

    return results


def export_data_to_files(
    data: List[Dict[str, Any]],
    output_prefix: str,
    output_dir: Path,
) -> Dict[str, str]:
    if not data:
        print("[!] 没有可导出的数据。")
        return {}

    df = pd.DataFrame(data)
    
    excel_path = output_dir / f"{output_prefix}.xlsx"
    csv_path = output_dir / f"{output_prefix}.csv"
    json_path = output_dir / f"{output_prefix}.json"

    df.to_excel(excel_path, index=False, engine="openpyxl")
    df.to_csv(csv_path, index=False, encoding="utf_8_sig")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "excel": str(excel_path),
        "csv": str(csv_path),
        "json": str(json_path),
    }


def calculate_bought_statistics(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    target_statuses = {"已评价", "待评价", "交易成功"}
    bought_items = [
        item for item in data
        if str(item.get("订单状态", "")).strip() in target_statuses
    ]

    total_goods_count = 0
    total_amount = 0.0

    seen_orders = {}
    for item in bought_items:
        try:
            qty = int(item.get("数量", 1) or 1)
        except Exception:
            qty = 1
        total_goods_count += qty

        order_sn = str(item.get("订单编号", "")).strip()
        try:
            order_amt = float(item.get("订单总金额(元)", 0) or 0)
        except Exception:
            order_amt = 0.0

        if order_sn:
            if order_sn not in seen_orders:
                seen_orders[order_sn] = order_amt
        else:
            try:
                price = float(item.get("单价(元)", 0) or 0)
                total_amount += price * qty
            except Exception:
                pass

    total_amount += sum(seen_orders.values())
    total_amount = round(total_amount, 2)

    status_counts = {}
    for st in ["交易成功", "已评价", "待评价"]:
        matched = [i for i in bought_items if str(i.get("订单状态", "")).strip() == st]
        status_counts[st] = {
            "records": len(matched),
            "quantity": sum(int(i.get("数量", 1) or 1) for i in matched)
        }

    return {
        "bought_records_count": len(bought_items),
        "total_goods_quantity": total_goods_count,
        "total_orders_count": len(seen_orders),
        "total_amount": total_amount,
        "status_counts": status_counts,
    }

