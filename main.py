# ZGQ Inc.
# https://t.me/ZGQinc

import sys
from config import AUTH_FILE
from export_favorites import PddFavoritesExporter
from export_orders import PddOrderExporter
from login import login


def show_menu():
    print("拼多多买家数据导出工具")
    print("=" * 50)
    print("1. 引导登录")
    print("2. 导出全部买家订单")
    print("3. 导出全部收藏")
    print("4. 一键执行全部 (登录 -> 导出订单 -> 导出收藏)")
    print("5. 统计已买到的商品 (已评价/待评价/交易成功)")
    print("0. 退出程序")
    print("=" * 50)


def show_statistics():
    import json
    from config import OUTPUT_DIR
    from utils import calculate_bought_statistics

    json_path = OUTPUT_DIR / "pdd_orders.json"
    if not json_path.exists():
        print("[!] 尚未找到订单导出数据，请先执行选项 2 导出订单。")
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        stats = calculate_bought_statistics(data)
        print("【已买到的商品消费统计】")
        print(f"[*] 商品数量: {stats['total_goods_quantity']} 件")
        print(f"[*] 实际成交订单笔数: {stats['total_orders_count']} 笔")
        print(f"[*] 实际消费总金额:   {stats['total_amount']:.2f} 元")
        for st, c in stats["status_counts"].items():
            print(f"    - {st}: {c['records']} 条明细, 共 {c['quantity']} 件")
    except Exception as e:
        print(f"[!] 读取统计数据失败: {e}")


def main():
    while True:
        show_menu()
        choice = input("请输入选项数字: ").strip()

        if choice == "1":
            login()
        elif choice == "2":
            if not AUTH_FILE.exists():
                print("[!] 尚未登录，正在启动登录流程...")
                if login():
                    exporter = PddOrderExporter(headless=False)
                    exporter.run()
            else:
                exporter = PddOrderExporter(headless=False)
                exporter.run()
        elif choice == "3":
            if not AUTH_FILE.exists():
                print("[!] 尚未登录，正在启动登录流程...")
                if login():
                    exporter = PddFavoritesExporter(headless=False)
                    exporter.run()
            else:
                exporter = PddFavoritesExporter(headless=False)
                exporter.run()
        elif choice == "4":
            if not AUTH_FILE.exists():
                if not login():
                    print("[X] 登录中断，取消后续操作。")
                    continue
            print("\n>>> 开始导出订单数据...")
            order_exporter = PddOrderExporter(headless=False)
            order_exporter.run()

            print("\n>>> 开始导出收藏数据...")
            fav_exporter = PddFavoritesExporter(headless=False)
            fav_exporter.run()
            print("\n[√] 全部任务已执行完毕！")
        elif choice == "5":
            show_statistics()
        elif choice == "0":
            print("感谢使用，再见！")
            sys.exit(0)
        else:
            print("[!] 无效输入，请重新选择。")


if __name__ == "__main__":
    main()
