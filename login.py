import datetime
import json
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, Page, sync_playwright

from config import (
    AUTH_FILE,
    MOBILE_USER_AGENT,
    MOBILE_VIEWPORT,
    PDD_BASE_URL,
    PDD_LOGIN_URL,
    PDD_PERSONAL_URL,
)


def is_logged_in(page: Page, context: BrowserContext) -> bool:
    try:
        cookies = context.cookies()
        token_cookies = [
            c for c in cookies if c["name"] == "PDDAccessToken" and c["value"]
        ]
        if token_cookies:
            for c in token_cookies:
                if c.get("expires", -1) > 0 and c["expires"] < time.time():
                    return False
            return True

        local_storage = page.evaluate("() => ({ ...localStorage })")
        if (
            local_storage.get("PDDAccessToken")
            or local_storage.get("pdd_user_id")
            or local_storage.get("user_id")
        ):
            return True

        if "login.html" not in page.url:
            has_logged_in_features = page.evaluate("""() => {
                const text = document.body ? document.body.innerText : "";
                const isLoginPage = text.includes("手机号登录") || text.includes("请输入手机号码") || text.includes("获取验证码");
                const isPersonalPage = text.includes("我的订单") || text.includes("退款/售后") || text.includes("商品收藏");
                return isPersonalPage && !isLoginPage;
            }""")
            if has_logged_in_features:
                return True

    except Exception:
        pass
    return False


def login():
    print("【拼多多买家登录引导】")
    print("1. 即将为您启动浏览器窗口...")
    print("2. 请在弹出的手机版网页中，输入【手机号 + 验证码】完成登录。")
    print("3. 登录成功后系统会自动检测并持久化保存会话凭证。")

    with sync_playwright() as playwright:
        from utils import get_mobile_context
        context = get_mobile_context(playwright, headless=False)
        page = context.pages[0] if context.pages else context.new_page()

        print("[*] 正在打开拼多多移动端页面...")
        try:
            page.goto(PDD_PERSONAL_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
        except Exception as e:
            print(f"[*] 页面加载提示: {e}")

        if is_logged_in(page, context):
            print("[√] 检测到已处于有效登录状态！")
        else:
            print("[*] 跳转到登录页面，请在弹出的浏览器中操作...")
            try:
                page.goto(PDD_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            print("[*] 等待用户完成登录中 (最长等待 5 分钟)...")
            max_wait_seconds = 300
            start_time = time.time()
            logged_in = False
            last_tick = 0

            while time.time() - start_time < max_wait_seconds:
                time.sleep(2)
                elapsed = int(time.time() - start_time)
                if elapsed - last_tick >= 10:
                    last_tick = elapsed
                    print(f"[*] 仍在等待登录中... (已等待 {elapsed} 秒)")

                if is_logged_in(page, context):
                    logged_in = True
                    break

            if not logged_in:
                try:
                    page.goto(PDD_PERSONAL_URL, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(2)
                    if is_logged_in(page, context):
                        logged_in = True
                except Exception:
                    pass

            if not logged_in:
                print("[X] 登录超时或未检测到登录状态，请重新运行登录脚本。")
                context.close()
                return False

        context.storage_state(path=str(AUTH_FILE))
        print(f"\n[√] 登录成功！凭证已保存至: {AUTH_FILE}")
        
        try:
            page.goto(PDD_PERSONAL_URL, wait_until="domcontentloaded", timeout=15000)
            time.sleep(1)
            print("[√] 成功访问个人中心！后续导出无需重复登录。")
        except Exception:
            pass

        time.sleep(2)
        context.close()
        return True


if __name__ == "__main__":
    login()
