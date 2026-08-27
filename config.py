import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
AUTH_FILE = BASE_DIR / "auth.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
AUTO_SAVE_INTERVAL = 10

PDD_BASE_URL = "https://mobile.yangkeduo.com"
PDD_LOGIN_URL = "https://mobile.yangkeduo.com/login.html"
PDD_ORDERS_URL = "https://mobile.yangkeduo.com/orders.html?type=0"
PDD_PERSONAL_URL = "https://mobile.yangkeduo.com/personal.html"
PDD_FAV_GOODS_URL = "https://mobile.yangkeduo.com/likes.html"
PDD_FAV_MALL_URL = "https://mobile.yangkeduo.com/psnl_mall_collection.html"
PDD_FOOTPRINT_URL = "https://mobile.yangkeduo.com/footprint.html"

MOBILE_VIEWPORT = {"width": 393, "height": 852}
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)

SCROLL_INTERVAL = 1.2
MAX_IDLE_SCROLLS = 18
