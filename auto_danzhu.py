#!/usr/bin/env python3
"""
Auto Login & Nhap Ma Moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)

Flow:
  1. Lay DataDome cookie (Playwright tu dong hoac --datadome thu cong)
  2. Garena Connect OAuth: prelogin -> login -> token/grant -> token/exchange
  3. ITOP Game Login: get aov_token, GameOpenId, gameToken
  4. AOV Cloud: danzhu/usecode - nhap ma moi ban be

Cach dung:
  # Cach 1: Tu dong bang Playwright (can may tinh co Chrome)
  pip install playwright curl_cffi
  python3 auto_danzhu.py --accounts accounts.txt --code MA_MOI

  # Cach 2: Thu cong (phu hop Termux/Android)
  # Buoc 1: Lay cookie
  python3 auto_danzhu.py --get-cookie
  # Buoc 2: Chay voi cookie
  python3 auto_danzhu.py -a accounts.txt -c MA_MOI --datadome "COOKIE_VALUE"

accounts.txt format (moi dong 1 tai khoan):
  username:password
  email:password
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import re

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    import requests as std_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

GARENA_APP_ID = "100054"
GARENA_CLIENT_SECRET = "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515"
GARENA_REDIRECT_URI = "gop100054://auth/"
GARENA_CONNECT_BASE = "https://100054.connect.garena.com"

ITOP_BASE = "https://itop.kg.garena.vn"
ITOP_GAMEID = "1137"
ITOP_CHANNELID = "10"

AOV_CLOUD_BASE = "https://aovcloud.garena.com"
AOV_PARTITION = "1011"
AOV_AREA_ID = "1"

BROWSER_UA = (
    "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.46 "
    "Mobile Safari/537.36"
)
UNITY_UA = "UnityPlayer/2022.3.5f1 (UnityWebRequest/1.0, libcurl/8.1.1-DEV)"
SDK_UA = "GarenaMSDK/4.0.38(SM-A165F ;Android 15;vi;VN;)"

OAUTH_URL = (
    f"{GARENA_CONNECT_BASE}/universal/oauth?"
    f"redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
    f"&response_type=code&client_id={GARENA_APP_ID}"
    f"&login_scenario=normal&locale=vi-VN"
)


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def garena_password_hash(password: str, v2: str) -> str:
    return md5(md5(password) + v2)


def ts_ms() -> str:
    return str(int(time.time() * 1000))


def find_chromium_path():
    """Tim duong dan Chromium tren he thong."""
    import shutil
    import os
    import glob

    pw_paths = glob.glob("/opt/pw-browsers/chromium*/chrome-linux/chrome")
    if pw_paths:
        return pw_paths[0]

    for name in ["chromium", "chromium-browser", "google-chrome", "chrome"]:
        p = shutil.which(name)
        if p:
            return p

    common = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/snap/bin/chromium",
    ]
    for p in common:
        if os.path.isfile(p):
            return p

    return None


def get_datadome_cookie_playwright(timeout_sec=45):
    """
    Dung Playwright mo trang OAuth cua Garena, cho DataDome tags.js chay,
    doi interstitial device check hoan tat, lay cookie da validate.
    """
    if not HAS_PLAYWRIGHT:
        return ""

    chrome_path = find_chromium_path()
    if not chrome_path:
        print("  [!] Khong tim thay Chromium. Cai dat: playwright install chromium")
        return ""

    print("  [*] Dang mo trinh duyet de lay DataDome cookie...")

    try:
        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]

            browser = p.chromium.launch(
                headless=True,
                executable_path=chrome_path,
                args=launch_args,
            )

            context = browser.new_context(
                user_agent=BROWSER_UA,
                viewport={"width": 412, "height": 915},
                device_scale_factor=2.625,
                is_mobile=True,
                has_touch=True,
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                extra_http_headers={
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "X-Requested-With": "com.garena.game.kgvn",
                },
                ignore_https_errors=True,
            )

            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['vi-VN', 'vi', 'en-US', 'en']
                });
                window.chrome = { runtime: {} };
            """)

            page = context.new_page()

            interstitial_cookies = []
            datadome_cookies = []

            def on_response(response):
                url = response.url
                try:
                    if response.status == 200 and response.request.method == "POST":
                        if "captcha-delivery.com/interstitial" in url:
                            body = response.text()
                            data = json.loads(body)
                            if data.get("view") == "redirect":
                                cookie_str = data.get("cookie", "")
                                if "datadome=" in cookie_str:
                                    val = cookie_str.split("datadome=")[1].split(";")[0]
                                    interstitial_cookies.append(val)
                                    print(f"  [+] Interstitial validated!")
                        elif "datadome" in url and "/js/" in url:
                            body = response.text()
                            if '"cookie"' in body and "datadome=" in body:
                                data = json.loads(body)
                                cookie_str = data.get("cookie", "")
                                if "datadome=" in cookie_str:
                                    val = cookie_str.split("datadome=")[1].split(";")[0]
                                    datadome_cookies.append(val)
                except Exception:
                    pass

            page.on("response", on_response)

            print(f"  [*] Dang tai trang Garena OAuth...")
            page.goto(OAUTH_URL, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            print(f"  [*] Trang da tai, cho DataDome xu ly...")

            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if interstitial_cookies:
                    break
                page.wait_for_timeout(500)

            cookie_value = ""
            if interstitial_cookies:
                cookie_value = interstitial_cookies[-1]
                print(f"  [+] DataDome cookie (interstitial): {cookie_value[:40]}...")
            else:
                cookies = context.cookies()
                for c in cookies:
                    if c["name"] == "datadome":
                        cookie_value = c["value"]
                        break
                if not cookie_value and datadome_cookies:
                    cookie_value = datadome_cookies[-1]
                if cookie_value:
                    print(f"  [+] DataDome cookie (browser): {cookie_value[:40]}...")
                else:
                    print("  [!] Khong lay duoc DataDome cookie")

            browser.close()
            return cookie_value

    except Exception as e:
        print(f"  [!] Playwright loi: {e}")
        return ""


def print_cookie_instructions():
    """In huong dan lay datadome cookie thu cong."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           HUONG DAN LAY DATADOME COOKIE THU CONG            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Buoc 1: Mo link sau trong trinh duyet dien thoai:           ║
║                                                              ║
║  https://100054.connect.garena.com/universal/oauth?           ║
║    redirect_uri=gop100054%3A%2F%2Fauth%2F                    ║
║    &response_type=code&client_id=100054                      ║
║    &login_scenario=normal&locale=vi-VN                       ║
║                                                              ║
║  Buoc 2: Doi trang login hien ra (khoang 3-5 giay)          ║
║                                                              ║
║  Buoc 3: Lay cookie datadome:                                ║
║    - Chrome: F12 -> Application -> Cookies -> garena.com     ║
║    - Firefox: F12 -> Storage -> Cookies -> garena.com        ║
║    - Tim cookie ten "datadome", copy gia tri                 ║
║                                                              ║
║  Buoc 4: Chay tool voi cookie:                               ║
║    python3 auto_danzhu.py -a accounts.txt -c MA_MOI \\        ║
║      --datadome "GIA_TRI_COOKIE"                             ║
║                                                              ║
║  Tren Termux/Android:                                        ║
║    - Dung app "Cookie Editor" tren Chrome                    ║
║    - Hoac dung Kiwi Browser (co DevTools)                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


def create_session(datadome_cookie=""):
    if HAS_CURL_CFFI:
        session = curl_requests.Session(impersonate="chrome120")
    elif HAS_REQUESTS:
        session = std_requests.Session()
    else:
        raise RuntimeError("Can curl_cffi hoac requests. Cai: pip install curl_cffi")

    if datadome_cookie:
        session.cookies.set("datadome", datadome_cookie, domain=".garena.com")

    return session


def http_get(session, url, headers, timeout=15):
    return session.get(url, headers=headers, timeout=timeout)


def http_post(session, url, data=None, headers=None, timeout=15):
    return session.post(url, data=data, headers=headers, timeout=timeout)


def garena_login(session, account: str, password: str) -> dict:
    common_headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "com.garena.game.kgvn",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Android WebView";v="150"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": OAUTH_URL,
    }

    # Step 1: Prelogin - lay v2 salt
    prelogin_url = (
        f"{GARENA_CONNECT_BASE}/api/prelogin?"
        f"app_id={GARENA_APP_ID}"
        f"&account={urllib.parse.quote(account)}"
        f"&format=json&id={ts_ms()}"
    )
    resp = http_get(session, prelogin_url, common_headers)

    if resp.status_code == 403:
        try:
            err_data = resp.json()
            if "url" in err_data and "captcha-delivery" in err_data.get("url", ""):
                raise RuntimeError(
                    f"DataDome captcha! Cookie da het han hoac khong hop le.\n"
                    f"  -> Lay cookie moi: python3 auto_danzhu.py --get-cookie"
                )
        except (ValueError, KeyError):
            pass
        raise RuntimeError(f"Prelogin 403 - DataDome chan. Dung --datadome COOKIE")

    resp.raise_for_status()
    prelogin_data = resp.json()
    v2 = prelogin_data.get("v2", "")
    if not v2:
        raise RuntimeError(f"Prelogin khong tra ve v2: {prelogin_data}")

    # Step 2: Login - gui password da hash
    pw_hash = garena_password_hash(password, v2)
    login_url = (
        f"{GARENA_CONNECT_BASE}/api/login?"
        f"app_id={GARENA_APP_ID}"
        f"&account={urllib.parse.quote(account)}"
        f"&password={pw_hash}"
        f"&redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&format=json&id={ts_ms()}"
    )
    resp = http_get(session, login_url, common_headers)
    if resp.status_code == 403:
        raise RuntimeError(f"Login 403 - DataDome chan.")
    resp.raise_for_status()
    login_data = resp.json()
    if "error" in login_data:
        err_msg = login_data.get("error", "")
        err_desc = login_data.get("description", login_data.get("msg", ""))
        raise RuntimeError(f"Login loi: {err_msg} - {err_desc}")
    session_key = login_data.get("session_key", "")
    uid = login_data.get("uid", "")
    if not session_key:
        raise RuntimeError(f"Login khong co session_key: {login_data}")
    print(f"  [+] Garena login OK: uid={uid}")

    # Step 3: Token Grant - lay authorization code
    grant_url = f"{GARENA_CONNECT_BASE}/oauth/token/grant"
    grant_headers = {
        **common_headers,
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": GARENA_CONNECT_BASE,
    }
    grant_data = (
        f"client_id={GARENA_APP_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&login_scenario=normal"
        f"&format=json"
        f"&id={ts_ms()}"
    )
    resp = http_post(session, grant_url, data=grant_data, headers=grant_headers)
    resp.raise_for_status()
    grant_result = resp.json()
    code = grant_result.get("code", "")
    if not code:
        raise RuntimeError(f"Token grant khong co code: {grant_result}")

    # Step 4: Token Exchange - lay access_token (dung SDK UA)
    exchange_url = f"{GARENA_CONNECT_BASE}/oauth/token/exchange"
    exchange_data = (
        f"code={code}"
        f"&grant_type=authorization_code"
        f"&login_scenario=normal"
        f"&redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&source=2"
        f"&client_secret={GARENA_CLIENT_SECRET}"
        f"&client_id={GARENA_APP_ID}"
    )
    if HAS_CURL_CFFI:
        exchange_session = curl_requests.Session(impersonate="chrome120")
    elif HAS_REQUESTS:
        exchange_session = std_requests.Session()
    resp = exchange_session.post(exchange_url, data=exchange_data, headers={
        "User-Agent": SDK_UA,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    resp.raise_for_status()
    exchange_result = resp.json()
    access_token = exchange_result.get("access_token", "")
    open_id = exchange_result.get("open_id", "")
    garena_uid = exchange_result.get("uid", "")
    if not access_token:
        raise RuntimeError(f"Token exchange khong co access_token: {exchange_result}")
    print(f"  [+] Token exchange OK: open_id={open_id[:16]}...")

    return {
        "access_token": access_token,
        "open_id": open_id,
        "uid": garena_uid,
        "session_key": session_key,
    }


def itop_login(access_token: str, open_id: str) -> dict:
    ts = str(int(time.time()))
    seq_id = f"{ITOP_GAMEID}-auto-{ts}"

    body = json.dumps({
        "openid": open_id,
        "token": access_token,
        "channelid": int(ITOP_CHANNELID),
        "gameid": int(ITOP_GAMEID),
        "os": 1,
        "lang": "",
        "seq": seq_id,
        "ts": ts,
    })

    params = (
        f"channelid={ITOP_CHANNELID}"
        f"&encrypt=0"
        f"&gameid={ITOP_GAMEID}"
        f"&lang="
        f"&os=1"
        f"&seq={seq_id}"
        f"&ts={ts}"
        f"&version=null"
    )

    url = f"{ITOP_BASE}/v2/auth/login?{params}"
    headers = {
        "Content-Type": "application/json",
        "Host": "itop.kg.garena.vn",
    }

    if HAS_CURL_CFFI:
        resp = curl_requests.post(url, data=body, headers=headers, timeout=15)
    elif HAS_REQUESTS:
        resp = std_requests.post(url, data=body, headers=headers, timeout=15)
    else:
        raise RuntimeError("Can curl_cffi hoac requests")
    resp.raise_for_status()

    try:
        result = resp.json()
    except Exception:
        raise RuntimeError(f"ITOP khong tra ve JSON: {resp.text[:200]}")

    if result.get("ret", -1) != 0:
        raise RuntimeError(f"ITOP loi: ret={result.get('ret')}, msg={result.get('msg','')}")

    token_info = result.get("token_info", {})
    aov_token = token_info.get("aov_token", result.get("aov_token", ""))
    game_openid = result.get("openid", token_info.get("openid", ""))
    game_token = token_info.get("game_token", result.get("game_token", ""))

    return {
        "aov_token": aov_token,
        "game_openid": game_openid,
        "game_token": game_token,
        "raw": result,
    }


def use_invitation_code(aov_token, game_openid, game_token, invitation_code):
    url = f"{AOV_CLOUD_BASE}/vn_online/danzhu/usecode"

    userinfo = json.dumps({
        "uin": game_openid,
        "areaID": AOV_AREA_ID,
        "roleID": game_openid,
        "platform": "1",
        "accType": "Guest",
        "partitionID": AOV_PARTITION,
    }, separators=(",", ":"))

    headers = {
        "Host": "aovcloud.garena.com",
        "User-Agent": UNITY_UA,
        "Accept": "*/*",
        "Content-Type": "application/json; charset=utf-8",
        "aov_token": aov_token,
        "GameOpenId": game_openid,
        "gameToken": game_token,
        "channel": "1",
        "platId": "1",
        "partition": AOV_PARTITION,
        "areaId": AOV_AREA_ID,
        "userinfo": userinfo,
        "lang": "VN",
        "version": "0.0.6",
        "gmTimeStamp": str(int(time.time())),
        "X-Unity-Version": "2022.3.5f1",
    }

    body = json.dumps({"invitationCode": invitation_code})
    if HAS_CURL_CFFI:
        resp = curl_requests.post(url, data=body, headers=headers, timeout=15)
    elif HAS_REQUESTS:
        resp = std_requests.post(url, data=body, headers=headers, timeout=15)
    else:
        raise RuntimeError("Can curl_cffi hoac requests")
    resp.raise_for_status()
    return resp.json()


def process_account(account, password, invitation_code, datadome_cookie="", delay=2.0):
    print(f"\n{'='*60}")
    print(f"[*] Dang xu ly: {account}")
    print(f"{'='*60}")

    dd_cookie = datadome_cookie

    if not dd_cookie and HAS_PLAYWRIGHT:
        dd_cookie = get_datadome_cookie_playwright(timeout_sec=40)
        if not dd_cookie:
            print("  [!] Playwright khong lay duoc cookie, thu khong co cookie...")

    session = create_session(dd_cookie)

    # Step 1: Garena Connect login
    try:
        garena_result = garena_login(session, account, password)
    except Exception as e:
        print(f"  [!] Garena login THAT BAI: {e}")
        return False

    time.sleep(delay)

    # Step 2: ITOP Game login
    try:
        itop_result = itop_login(
            garena_result["access_token"],
            garena_result["open_id"],
        )
        print(f"  [+] ITOP login OK: GameOpenId={itop_result['game_openid']}")
    except Exception as e:
        print(f"  [!] ITOP login THAT BAI: {e}")
        return False

    time.sleep(delay)

    # Step 3: Nhap ma moi
    try:
        result = use_invitation_code(
            itop_result["aov_token"],
            itop_result["game_openid"],
            itop_result["game_token"],
            invitation_code,
        )
        code = result.get("code", -1)
        msg = result.get("msg", "")
        reward = result.get("rewardDanzhuNum", 0)

        if code == 0:
            print(f"  [+] NHAP MA THANH CONG! Reward: {reward} dan chu")
            invite_data = result.get("inviteData", {})
            own_code = invite_data.get("invitationCode", "")
            if own_code:
                print(f"  [+] Ma moi cua tai khoan nay: {own_code}")
        else:
            print(f"  [!] Nhap ma that bai: code={code}, msg={msg}")
        return code == 0
    except Exception as e:
        print(f"  [!] Nhap ma loi: {e}")
        return False


def load_accounts(filepath):
    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            idx = line.find(":")
            if idx == -1:
                print(f"  [!] Dong {line_num} sai format (can account:password): {line}")
                continue
            account = line[:idx].strip()
            password = line[idx+1:].strip()
            if account and password:
                accounts.append((account, password))
    return accounts


def main():
    parser = argparse.ArgumentParser(
        description="Auto nhap ma moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Vi du:
  # Tu dong (can Playwright + Chrome):
  python3 auto_danzhu.py -a accounts.txt -c 7Fr64s5RL6

  # Thu cong (Termux/Android):
  python3 auto_danzhu.py --get-cookie
  python3 auto_danzhu.py -a accounts.txt -c 7Fr64s5RL6 --datadome "COOKIE"

  # Dung chung 1 cookie cho nhieu tai khoan:
  python3 auto_danzhu.py -a accounts.txt -c 7Fr64s5RL6 --datadome "COOKIE"
        """
    )
    parser.add_argument("--accounts", "-a",
        help="File danh sach tai khoan (account:password)")
    parser.add_argument("--code", "-c",
        help="Ma moi ban be can nhap (vd: 7Fr64s5RL6)")
    parser.add_argument("--delay", "-d", type=float, default=3.0,
        help="Delay giua cac buoc (giay, mac dinh: 3)")
    parser.add_argument("--account-delay", type=float, default=5.0,
        help="Delay giua cac tai khoan (giay, mac dinh: 5)")
    parser.add_argument("--datadome", default="",
        help="DataDome cookie (lay tu trinh duyet)")
    parser.add_argument("--get-cookie", action="store_true",
        help="Hien huong dan lay DataDome cookie thu cong")
    args = parser.parse_args()

    if args.get_cookie:
        if HAS_PLAYWRIGHT:
            print("[*] Dang thu lay cookie bang Playwright...")
            cookie = get_datadome_cookie_playwright(timeout_sec=45)
            if cookie:
                print(f"\n[+] THANH CONG! DataDome cookie:")
                print(f"\n    {cookie}\n")
                print(f"[*] Chay tool voi cookie nay:")
                print(f'    python3 auto_danzhu.py -a accounts.txt -c MA_MOI --datadome "{cookie}"')
            else:
                print("\n[!] Playwright khong lay duoc cookie.")
                print_cookie_instructions()
        else:
            print_cookie_instructions()
        return

    if not args.accounts or not args.code:
        parser.print_help()
        print("\n[!] Can --accounts va --code. Hoac dung --get-cookie de lay cookie truoc.")
        sys.exit(1)

    print(f"[*] HTTP: {'curl_cffi (Chrome TLS)' if HAS_CURL_CFFI else 'requests'}")
    print(f"[*] Playwright: {'co' if HAS_PLAYWRIGHT else 'khong'}")

    if not HAS_PLAYWRIGHT and not args.datadome:
        print()
        print("[!] CANH BAO: Khong co Playwright va khong co --datadome cookie!")
        print("[!] Se bi DataDome chan. Cach xu ly:")
        print("[!]   1. Cai Playwright: pip install playwright && playwright install chromium")
        print("[!]   2. Hoac lay cookie: python3 auto_danzhu.py --get-cookie")
        print()

    accounts = load_accounts(args.accounts)
    if not accounts:
        print("[!] Khong tim thay tai khoan nao trong file.")
        sys.exit(1)

    print(f"[*] So tai khoan: {len(accounts)}")
    print(f"[*] Ma moi: {args.code}")
    if args.datadome:
        print(f"[*] DataDome cookie: {args.datadome[:40]}...")

    success = 0
    fail = 0

    for i, (account, password) in enumerate(accounts):
        if i > 0:
            print(f"\n[*] Cho {args.account_delay}s truoc tai khoan tiep...")
            time.sleep(args.account_delay)

        ok = process_account(account, password, args.code, args.datadome, args.delay)
        if ok:
            success += 1
        else:
            fail += 1

    print(f"\n{'='*60}")
    print(f"[*] KET QUA: {success} thanh cong, {fail} that bai / {len(accounts)} tong")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
