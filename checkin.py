#!/usr/bin/env python3
"""
Nikki4-webcheckin
=================

《閃耀暖暖》官網「簽到有禮」每日自動簽到 + 兌換禮物。

流程（與網頁上手機版的操作一致）：
  1. 用手機模擬（mobile emulation）開啟 https://nikki4.com.tw/checkin/sign?activity_id=0
  2. 點「登錄」→「信箱登錄」，輸入信箱與密碼
  3. 關閉「歡迎，XXX」彈窗
  4. 點「簽到」
  5. 讀取本月積分與簽到天數
  6. 依優先順序前往 /checkin/gift?activity_id=0 兌換獎勵

結構上沿用 simao-silva/noip-renewer 的做法：無頭瀏覽器 + 一次性執行 + 明確的
退出碼，跑完就結束（容器用 --rm 會自動移除）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

BASE = os.getenv("SITE", "https://nikki4.com.tw").rstrip("/")
SIGN_URL = os.getenv("SIGN_URL", f"{BASE}/checkin/sign?activity_id=0")
GIFT_URL = os.getenv("GIFT_URL", f"{BASE}/checkin/gift?activity_id=0")

#: The activity API the page itself talks to.
API_BASE = os.getenv("API_BASE", "https://nikki4fbtw.papegames.com/api/v1/activity/0")

EMAIL = os.getenv("NIKKI_EMAIL") or os.getenv("USERNAME") or ""
PASSWORD = os.getenv("NIKKI_PASSWORD") or os.getenv("PASSWORD") or ""

BROWSER = os.getenv("BROWSER", "chrome").strip().lower()
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() not in {"0", "false", "no"}
DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes"}

#: Redeem rewards after signing in (set to false to only check in).
REDEEM = os.getenv("REDEEM", "true").strip().lower() not in {"0", "false", "no"}
#: Print the redemption plan without clicking anything.
DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in {"1", "true", "yes"}

#: Do not touch the gift shop before this many check-ins this month.
MIN_SIGNED_DAYS = int(os.getenv("MIN_SIGNED_DAYS", "30"))

#: Priority list: name -> (points, monthly limit).  First match wins, and the
#: bot redeems greedily while points allow and the monthly limit is not reached.
DEFAULT_PLAN = [
    {"name": "粉鑽", "cost": 25, "limit": 2},
    {"name": "幻券體力禮包", "cost": 120, "limit": 1},
    {"name": "記憶鑰匙禮包", "cost": 80, "limit": 1},
    {"name": "記憶之軌", "cost": 25, "limit": 2},
    {"name": "謎之券", "cost": 25, "limit": 2},
    {"name": "印象碎片", "cost": 10, "limit": 3},
    {"name": "體力", "cost": 10, "limit": 3},
    {"name": "金幣", "cost": 10, "limit": 3},
    {"name": "30天連簽獎勵", "cost": 0, "limit": 1, "requires_streak": 30},
]

try:
    PLAN = json.loads(os.getenv("REDEEM_PLAN", "")) or DEFAULT_PLAN
except json.JSONDecodeError:
    PLAN = DEFAULT_PLAN

LOGIN_TIMEOUT = float(os.getenv("LOGIN_TIMEOUT", "90"))
ACTION_TIMEOUT = float(os.getenv("ACTION_TIMEOUT", "30"))
ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "/app/artifacts"))

MOBILE = json.loads(
    os.getenv(
        "MOBILE_EMULATION",
        '{"deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0, '
        '"touch": true, "mobile": true}, '
        '"userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"}',
    )
)

# DOM hooks taken from the site's own bundle (stable class / ga-data names).
SEL_LOGIN_BTN = ".btn-login, [ga-data='ck-login']"
SEL_MAIL_OPTION = ".modal-login-mail, [ga-data='click-login-mail']"
SEL_EMAIL_INPUT = "input[type='text'][placeholder*='信箱']"
SEL_PASSWORD_INPUT = "input[type='password']"
SEL_LOGIN_SUBMIT = ".modal-login-btn-login, [ga-data='click-login']"
SEL_POPUP_CLOSE = ".modal-login-btn-confirm, .pop-btn-confirm, .btn-confirm"
SEL_SIGN_BTN = ".btn-sign, [ga-data='ck-sign']"
SEL_SIGNED_BTN = ".btn-signed, [ga-data='ck-signed']"
SEL_CREDIT = ".credit-info"
SEL_SIGNED_INFO = ".signed-info"
SEL_EXCHANGE = ".btn-exchange[ga-data^='ck-gift-']"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def visible(element) -> bool:
    try:
        return bool(element.is_displayed())
    except (StaleElementReferenceException, WebDriverException):
        return False


def first_visible(driver, css: str, timeout: float = 0.0):
    deadline = time.time() + timeout
    while True:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, css):
                if visible(element):
                    return element
        except WebDriverException:
            pass
        if time.time() >= deadline:
            return None
        time.sleep(0.3)


def click(driver, element) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    except (JavascriptException, StaleElementReferenceException):
        pass
    try:
        element.click()
        return True
    except (ElementClickInterceptedException, ElementNotInteractableException):
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except (JavascriptException, StaleElementReferenceException):
            return False
    except (StaleElementReferenceException, WebDriverException):
        return False


def save_artifacts(driver, tag: str) -> None:
    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        driver.save_screenshot(str(ARTIFACTS_DIR / f"{stamp}-{tag}.png"))
        (ARTIFACTS_DIR / f"{stamp}-{tag}.html").write_text(driver.page_source, encoding="utf-8")
        log(f"Debug artifacts written to {ARTIFACTS_DIR}")
    except Exception as exc:
        log(f"Could not write artifacts: {exc}")


def page_text(driver) -> str:
    try:
        return norm(driver.find_element(By.TAG_NAME, "body").text)
    except WebDriverException:
        return ""


# --------------------------------------------------------------------------- #
# Browser (mobile emulation)
# --------------------------------------------------------------------------- #


def build_driver():
    driver_path = os.getenv("WEBDRIVER_PATH")
    profile_dir = os.getenv("BROWSER_PROFILE_DIR")
    if not driver_path:
        for candidate in ("/usr/bin/chromedriver", "/usr/bin/geckodriver"):
            if Path(candidate).exists():
                driver_path = candidate
                break

    if BROWSER in {"firefox"}:
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        from selenium.webdriver.firefox.service import Service as FirefoxService

        options = FirefoxOptions()
        if HEADLESS:
            options.add_argument("-headless")
        options.set_preference("general.useragent.override", MOBILE["userAgent"])
        options.set_preference("intl.accept_languages", "zh-TW,zh")
        service = FirefoxService(executable_path=driver_path) if driver_path else FirefoxService()
        log("Starting Firefox (narrow viewport + mobile UA)")
        driver = webdriver.Firefox(options=options, service=service)
        driver.set_window_size(390, 844)
        return driver

    if BROWSER in {"edge", "msedge"}:
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService

        options = EdgeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--lang=zh-TW")
        if profile_dir:
            options.add_argument(f"--user-data-dir={Path(profile_dir).absolute()}")
        options.add_experimental_option("mobileEmulation", MOBILE)
        service = EdgeService(executable_path=driver_path) if driver_path else EdgeService()
        log("Starting Edge with iPhone emulation")
        return webdriver.Edge(options=options, service=service)

    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService

    options = ChromeOptions()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=zh-TW")
    if profile_dir:
        options.add_argument(f"--user-data-dir={Path(profile_dir).absolute()}")
    options.add_experimental_option("mobileEmulation", MOBILE)
    service = ChromeService(executable_path=driver_path) if driver_path else ChromeService()
    log("Starting Chrome with iPhone emulation")
    return webdriver.Chrome(options=options, service=service)


# --------------------------------------------------------------------------- #
# In-page API access (uses the site's own session cookies)
# --------------------------------------------------------------------------- #


FETCH_JS = """
const out = {};
document.cookie.split('; ').forEach(function (c) {
    const i = c.indexOf('=');
    if (i > 0) out[c.slice(0, i)] = c.slice(i + 1);
});
return out;
"""


def session_params(driver) -> dict:
    """The activity API authenticates with query params, not the cookie jar."""
    try:
        return driver.execute_script(FETCH_JS) or {}
    except (JavascriptException, WebDriverException):
        return {}


def api(driver, path: str, method: str = "GET") -> dict | None:
    """Call the activity API from Python (no CORS involved)."""
    params = session_params(driver)
    if not params.get("nn4_token") or not params.get("nn4_nid"):
        log("No session cookies yet (not logged in)")
        return None

    query = urllib.parse.urlencode(
        {
            "nid": params.get("nn4_nid", ""),
            "token": params.get("nn4_token", ""),
            "platform": params.get("nn4_platform", ""),
            "zone": params.get("nn4_zone", ""),
        }
    )
    url = f"{API_BASE}{path}" + ("&" if "?" in path else "?") + query

    try:
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": MOBILE["userAgent"]}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        log(f"API {path} failed: {exc}")
        return None

    if data.get("ret") not in (0, None):
        log(f"API {path} returned ret={data.get('ret')} {data.get('msg', '')}")
    return data


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #


class LoginFailed(RuntimeError):
    pass


def dismiss_popups(driver) -> None:
    """Close the '歡迎，XXX' dialog and any other overlay in the way."""
    for _ in range(3):
        closed = False
        for selector in (SEL_POPUP_CLOSE, ".pop .cover", ".modal-login .cover"):
            element = first_visible(driver, selector, timeout=1)
            if element is not None and click(driver, element):
                log("Closed pop-up")
                closed = True
                time.sleep(0.8)
                break
        if not closed:
            return


def open_login_form(driver) -> None:
    button = first_visible(driver, SEL_LOGIN_BTN, timeout=10)
    if button is None:
        log("Login button not found (already logged in?)")
        return
    click(driver, button)
    time.sleep(1.0)

    mail = first_visible(driver, SEL_MAIL_OPTION, timeout=10)
    if mail is None:
        log("'信箱登錄' option not found, assuming the e-mail form is already open")
    else:
        click(driver, mail)
        time.sleep(0.8)


def popup_text(driver) -> str:
    """Text of the small modal the site uses for errors and greetings."""
    for selector in (".modal-login-pop", ".pop .pop-border > p", ".pop p", ".modal-login .pop"):
        element = first_visible(driver, selector, timeout=0)
        if element is not None:
            text = norm(element.text)
            if text:
                return text
    return ""


def do_login(driver, email: str, password: str) -> None:
    open_login_form(driver)

    field = first_visible(driver, SEL_EMAIL_INPUT, timeout=10)
    if field is None:
        raise LoginFailed("E-mail input did not appear")
    field.clear()
    field.send_keys(email)

    pwd = first_visible(driver, SEL_PASSWORD_INPUT, timeout=5)
    if pwd is None:
        raise LoginFailed("Password input did not appear")
    pwd.clear()
    pwd.send_keys(password)

    submit = first_visible(driver, SEL_LOGIN_SUBMIT, timeout=5)
    if submit is None:
        raise LoginFailed("Login submit button did not appear")
    click(driver, submit)
    log(f"Submitted credentials for {email}")

    deadline = time.time() + LOGIN_TIMEOUT
    while time.time() < deadline:
        # The site reports failures in a small modal -- read it before closing.
        message = popup_text(driver)
        if message:
            if message.startswith("歡迎"):
                log(f"Logged in ({message})")
                dismiss_popups(driver)
                return
            raise LoginFailed(message)

        # The role picker appears for accounts with several characters.
        if first_visible(driver, "input[name='client']", timeout=0) is not None:
            log("Role picker shown, taking the first character")
            labels = driver.find_elements(By.CSS_SELECTOR, "label[for^='client_']")
            if labels and click(driver, labels[0]):
                confirm = first_visible(driver, SEL_POPUP_CLOSE, timeout=5)
                if confirm is not None:
                    click(driver, confirm)
                time.sleep(2)

        if first_visible(driver, SEL_CREDIT, timeout=0) is not None or \
                first_visible(driver, SEL_SIGN_BTN, timeout=0) is not None or \
                first_visible(driver, SEL_SIGNED_BTN, timeout=0) is not None:
            log("Logged in")
            dismiss_popups(driver)
            return

        time.sleep(1.0)

    raise LoginFailed("Login did not complete (check the e-mail/password)")


# --------------------------------------------------------------------------- #
# Check-in
# --------------------------------------------------------------------------- #


def read_stats(driver) -> dict:
    """Prefer the API (exact numbers), fall back to the text on the page."""
    stats = {"credit": None, "days": None, "checkins": None}

    data = api(driver, "/credit")
    if data and data.get("ret") == 0:
        stats["credit"] = data.get("credit")

    data = api(driver, "/checkin/index")
    if data and data.get("ret") == 0:
        stats["days"] = data.get("days")
        stats["checkins"] = data.get("checkins")

    if stats["credit"] is None:
        element = first_visible(driver, SEL_CREDIT, timeout=3)
        if element is not None:
            match = re.search(r"(\d+)", norm(element.text))
            if match:
                stats["credit"] = int(match.group(1))

    if stats["days"] is None:
        element = first_visible(driver, SEL_SIGNED_INFO, timeout=3)
        if element is not None:
            match = re.search(r"（\s*(\d+)\s*/", norm(element.text))
            if match:
                stats["days"] = int(match.group(1))
    return stats


def check_in(driver) -> str:
    """Click 簽到; return 'signed', 'already' or 'failed'."""
    if first_visible(driver, SEL_SIGNED_BTN, timeout=3) is not None:
        log("Already signed in today")
        return "already"

    button = first_visible(driver, SEL_SIGN_BTN, timeout=10)
    if button is None:
        log("Sign button not found")
        return "failed"

    if not click(driver, button):
        log("Sign button could not be clicked")
        return "failed"

    deadline = time.time() + ACTION_TIMEOUT
    while time.time() < deadline:
        text = page_text(driver)
        if "簽到成功" in text:
            log("簽到成功")
            return "signed"
        if "今日已簽到" in text or "已經簽到" in text:
            log("Already signed in today")
            return "already"
        if first_visible(driver, SEL_SIGNED_BTN, timeout=0) is not None:
            log("Button switched to 已簽到")
            return "signed"
        time.sleep(0.5)

    log("No confirmation after clicking 簽到")
    return "failed"


# --------------------------------------------------------------------------- #
# Gift redemption
# --------------------------------------------------------------------------- #


def gift_catalog(driver) -> list[dict]:
    data = api(driver, "/gift/")
    if not data or data.get("ret") != 0:
        return []

    records = api(driver, "/gift/records")
    used = {}
    if records and records.get("ret") == 0:
        for record in records.get("records") or []:
            key = record.get("gift_id") or record.get("id")
            if key is not None:
                used[key] = used.get(key, 0) + 1

    catalog = []
    for item in data.get("gift") or data.get("gifts") or []:
        entry = dict(item)
        entry["_used"] = used.get(item.get("id"), 0)
        catalog.append(entry)
    return catalog


def plan_redemptions(catalog: list[dict], credit: int, signed_days: int, streak: int | None) -> list[dict]:
    """Walk the priority list and spend points greedily."""
    remaining = credit
    plan = []

    def lookup(name: str):
        for item in catalog:
            item_name = norm(str(item.get("name", "")))
            if name in item_name or item_name in name:
                return item
        return None

    for wanted in PLAN:
        item = lookup(wanted["name"])
        if item is None:
            log(f"Gift not in the shop: {wanted['name']}")
            continue

        cost = int(item.get("condition") or wanted.get("cost") or 0)
        limit = int(item.get("limit") or wanted.get("limit") or 1)
        used = int(item.get("_used") or 0)
        name = norm(str(item.get("name")))

        if wanted.get("requires_streak"):
            if (streak or 0) < wanted["requires_streak"]:
                log(f"Skip {name}: needs a {wanted['requires_streak']}-day streak, have {streak}")
                continue

        while used < limit and remaining >= cost:
            plan.append({"id": item.get("id"), "name": name, "cost": cost})
            used += 1
            remaining -= cost

        if used >= limit:
            log(f"Skip {name}: monthly limit reached ({used}/{limit})")

    return plan


def redeem(driver, plan: list[dict]) -> int:
    """Click the 兌換 button for each planned gift. Returns the number redeemed."""
    redeemed = 0
    for entry in plan:
        selector = f"{SEL_EXCHANGE}[ga-data='ck-gift-{entry['id']}']"
        button = first_visible(driver, selector, timeout=5)
        if button is None:
            log(f"Exchange button missing for {entry['name']}")
            continue
        if DRY_RUN:
            log(f"[dry-run] would redeem {entry['name']} for {entry['cost']} points")
            continue
        if not click(driver, button):
            log(f"Could not click 兌換 for {entry['name']}")
            continue

        time.sleep(1.5)
        dismiss_popups(driver)
        text = page_text(driver)
        if "兌換成功" in text or "恭喜" in text:
            redeemed += 1
            log(f"Redeemed {entry['name']} ({entry['cost']} points)")
        else:
            log(f"Redeem result for {entry['name']} unclear")
        time.sleep(1.0)
    return redeemed


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def get_credentials(args) -> tuple[str, str]:
    email = (args.email or EMAIL or "").strip()
    password = args.password or PASSWORD

    if not email and sys.stdin is not None and sys.stdin.isatty():
        email = input("E-mail: ").strip()
    if not password and sys.stdin is not None and sys.stdin.isatty():
        from getpass import getpass

        password = getpass("Password: ")

    if not email or not password:
        raise SystemExit(
            "Missing credentials.\n"
            "  Docker : docker run --rm -e NIKKI_EMAIL=<mail> -e NIKKI_PASSWORD=<pass> nikki4-webcheckin\n"
            "  Local  : python checkin.py --email <mail> --password <pass>"
        )
    return email, password


def main(argv: list[str] | None = None) -> int:
    global DEBUG

    parser = argparse.ArgumentParser(description="Nikki4 (閃耀暖暖) 每日簽到 + 兌換")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="sign in but do not redeem")
    parser.add_argument("--no-redeem", action="store_true")
    args = parser.parse_args(argv or sys.argv[1:])

    DEBUG = DEBUG or args.debug
    if args.dry_run:
        globals()["DRY_RUN"] = True
    if args.no_redeem:
        globals()["REDEEM"] = False

    try:
        email, password = get_credentials(args)
    except SystemExit as exc:
        log(str(exc))
        return EXIT_CONFIG

    log(f"Nikki4 web check-in -- {SIGN_URL}")
    driver = None

    try:
        driver = build_driver()
        driver.set_page_load_timeout(90)
        driver.get(SIGN_URL)
        log("Page loaded")
        dismiss_popups(driver)

        do_login(driver, email, password)

        status = check_in(driver)
        stats = read_stats(driver)
        log(f"Credit: {stats['credit']}  signed days: {stats['days']}")

        if not REDEEM:
            log("Redeem disabled")
            return EXIT_OK
        if status == "failed":
            log("Check-in failed, skipping redemption")
            return EXIT_FAIL
        if stats["days"] is not None and stats["days"] < MIN_SIGNED_DAYS:
            log(f"Only {stats['days']} check-ins this month (need {MIN_SIGNED_DAYS}), not redeeming yet")
            return EXIT_OK

        driver.get(GIFT_URL)
        time.sleep(2)
        dismiss_popups(driver)

        catalog = gift_catalog(driver)
        if not catalog:
            log("Could not read the gift catalog")
            save_artifacts(driver, "gift-catalog")
            return EXIT_FAIL

        streak = None
        data = api(driver, "/checkin/index")
        if data and data.get("ret") == 0:
            streak = data.get("continuous_days") or data.get("continuity")

        plan = plan_redemptions(catalog, int(stats["credit"] or 0), stats["days"] or 0, streak)
        if not plan:
            log("Nothing to redeem with the current points")
            return EXIT_OK

        done = redeem(driver, plan)
        log(f"Redeemed {done} gift(s)")
        return EXIT_OK if done else EXIT_FAIL

    except LoginFailed as exc:
        log(f"Login failed: {exc}")
        if driver is not None:
            save_artifacts(driver, "login-failed")
        return EXIT_FAIL
    except TimeoutException as exc:
        log(f"Timed out: {exc}")
        if driver is not None:
            save_artifacts(driver, "timeout")
        return EXIT_FAIL
    except WebDriverException as exc:
        log(f"Browser error: {exc.msg or exc}")
        if driver is not None:
            save_artifacts(driver, "browser-error")
        return EXIT_FAIL
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


if __name__ == "__main__":
    sys.exit(main())
