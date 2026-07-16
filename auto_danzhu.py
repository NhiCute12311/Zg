#!/usr/bin/env python3
"""
Auto Login & Nhap Ma Moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)

Cach dung:
  # Cach 1: Dung HAR file (lay DataDome tu dong, tot nhat)
  python3 auto_danzhu.py game.har -a accounts.txt -c MA_MOI

  # Cach 2: Replay session tu HAR (khong can dang nhap lai)
  python3 auto_danzhu.py game.har -c MA_MOI

  # Cach 3: Dung cookie thu cong (Termux/Android)
  python3 auto_danzhu.py -a accounts.txt -c MA_MOI --datadome "COOKIE"

  # Xem huong dan lay cookie
  python3 auto_danzhu.py --get-cookie

accounts.txt format (moi dong 1 tai khoan):
  username:password
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.parse

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
DD_KEY = "AE3F04AD3F0D3A462481A337485081"

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

DD_CACHE_FILE = ".dd_cookie"
HAR_CACHE_FILE = ".har_cache.json"
LOG_FILE = "auto_danzhu_log.txt"


def log(msg):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def garena_password_hash(password: str) -> str:
    return md5(password)


def ts_ms() -> str:
    return str(int(time.time() * 1000))


def do_request(method, url, data=None, headers=None, timeout=15):
    if HAS_CURL_CFFI:
        if method == "GET":
            return curl_requests.get(url, headers=headers, timeout=timeout)
        return curl_requests.post(url, data=data, headers=headers, timeout=timeout)
    elif HAS_REQUESTS:
        if method == "GET":
            return std_requests.get(url, headers=headers, timeout=timeout)
        return std_requests.post(url, data=data, headers=headers, timeout=timeout)
    raise RuntimeError("Can curl_cffi hoac requests. Cai: pip install curl_cffi requests")


# ── HAR PARSER ───────────────────────────────────────────────────────────────

def parse_har(har_path):
    """
    Trich xuat tu HAR:
    - sessions[]: acc da login san voi game tokens
    - template_cookies: cookies de fake browser state
    - datadome_cookie: cookie DataDome
    - jspl_payload: payload DataDome/js/ de refresh cookie
    """
    result = {
        "sessions": [],
        "template_cookies": {},
        "datadome_cookie": "",
        "jspl_payload": "",
    }

    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        har = json.load(f)
    entries = har["log"]["entries"]

    # 1. Template cookies tu prelogin request dau tien
    for e in entries:
        url = e["request"]["url"]
        if "api/prelogin" in url:
            cookies = {c["name"]: c["value"] for c in e["request"].get("cookies", [])}
            result["template_cookies"] = cookies
            result["datadome_cookie"] = cookies.get("datadome", "")
            break

    # 2. DataDome jspl payload
    for e in entries:
        url = e["request"]["url"]
        if "datadome.garena.com/js/" in url and e["request"]["method"] == "POST":
            body = e["request"].get("postData", {}).get("text", "")
            if "jspl=" in body:
                result["jspl_payload"] = body
                break

    # 3. Extract game sessions tu aovcloud requests
    sessions_map = {}
    for e in entries:
        url = e["request"]["url"]
        if "aovcloud.garena.com" not in url:
            continue
        hdrs = {h["name"]: h["value"] for h in e["request"]["headers"]}
        goid = hdrs.get("GameOpenId", "")
        gtok = hdrs.get("gameToken", "")
        atok = hdrs.get("aov_token", "")
        userinfo = hdrs.get("userinfo", "{}")

        if not (goid and gtok and atok):
            continue

        if goid not in sessions_map:
            sessions_map[goid] = {
                "GameOpenId": goid,
                "gameToken": gtok,
                "aov_token": atok,
                "userinfo": userinfo,
                "username": "",
            }

    # 4. Match login response -> username
    uid_to_user = {}
    for e in entries:
        url = e["request"]["url"]
        if "api/login" in url and "prelogin" not in url:
            try:
                data = json.loads(e["response"].get("content", {}).get("text", ""))
                if "uid" in data and "username" in data:
                    uid_to_user[str(data["uid"])] = data["username"]
            except Exception:
                pass

    usernames = list(uid_to_user.values())
    for i, (goid, sess) in enumerate(sessions_map.items()):
        if i < len(usernames):
            sess["username"] = usernames[i]

    result["sessions"] = list(sessions_map.values())

    # 5. Detect usecode endpoint (danzhu hoac tiaoyitiao)
    for e in entries:
        url = e["request"]["url"]
        if "aovcloud.garena.com" in url and "usecode" in url:
            if "tiaoyitiao" in url:
                result["usecode_path"] = "tiaoyitiao"
            elif "danzhu" in url:
                result["usecode_path"] = "danzhu"
            break

    save_har_cache(result["jspl_payload"], result["template_cookies"])
    return result


# ── DATADOME ─────────────────────────────────────────────────────────────────

def load_dd_cache():
    if os.path.exists(DD_CACHE_FILE):
        try:
            return open(DD_CACHE_FILE).read().strip()
        except Exception:
            pass
    return ""


def save_dd_cache(val):
    try:
        with open(DD_CACHE_FILE, "w") as f:
            f.write(val)
    except Exception:
        pass


def load_har_cache():
    if os.path.exists(HAR_CACHE_FILE):
        try:
            return json.load(open(HAR_CACHE_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_har_cache(jspl_payload, template_cookies):
    try:
        json.dump(
            {"jspl_payload": jspl_payload, "template_cookies": template_cookies},
            open(HAR_CACHE_FILE, "w", encoding="utf-8"),
        )
    except Exception:
        pass


def fetch_datadome(current_dd="", jspl_payload=""):
    """POST den datadome.garena.com/js/ voi jspl payload -> cookie moi."""
    url = "https://datadome.garena.com/js/"
    hdrs = {
        "User-Agent": BROWSER_UA,
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Android WebView";v="150"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "content-type": "application/x-www-form-urlencoded",
        "accept": "*/*",
        "origin": "https://100054.connect.garena.com",
        "x-requested-with": "com.garena.game.kgvn",
        "sec-fetch-site": "same-site",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "referer": "https://100054.connect.garena.com/",
        "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    if jspl_payload:
        payload = re.sub(
            r"cid=[^&]*",
            f"cid={urllib.parse.quote(current_dd)}",
            jspl_payload,
        )
    else:
        payload = (
            f"jspl=placeholder&eventCounters=%7B%7D&jsType=le"
            f"&cid={urllib.parse.quote(current_dd)}&ddk={DD_KEY}"
            f"&Referer=https%3A%2F%2F100054.connect.garena.com%2F"
            f"&request=%2Funiversal%2Foauth&responsePage=origin&ddv=5.8.0"
        )

    try:
        resp = do_request("POST", url, data=payload, headers=hdrs)
        data = resp.json()
        if data.get("status") == 200 and "cookie" in data:
            m = re.search(r"datadome=([^;]+)", data["cookie"])
            if m:
                return m.group(1)
    except Exception as e:
        log(f"  [!] DataDome fetch loi: {e}")
    return ""


def get_datadome(template_cookies=None, jspl_payload="", manual_cookie=""):
    """Lay DataDome cookie theo thu tu uu tien."""
    if manual_cookie:
        return manual_cookie

    template_cookies = template_cookies or {}

    # Load jspl tu cache neu khong co
    if not jspl_payload:
        cached = load_har_cache()
        if cached.get("jspl_payload"):
            jspl_payload = cached["jspl_payload"]
            log("  [*] Dung jspl cache tu HAR lan truoc")
        if not template_cookies and cached.get("template_cookies"):
            template_cookies = cached["template_cookies"]

    if jspl_payload:
        log("  [*] Dang lay DataDome cookie tu jspl replay...")
        current_dd = template_cookies.get("datadome", "") or load_dd_cache()
        new_dd = fetch_datadome(current_dd, jspl_payload)
        if new_dd:
            save_dd_cache(new_dd)
            log(f"  [+] DataDome OK: {new_dd[:45]}...")
            return new_dd
        # Retry voi cid rong
        if current_dd:
            log("  [*] Retry DataDome voi cid rong...")
            new_dd = fetch_datadome("", jspl_payload)
            if new_dd:
                save_dd_cache(new_dd)
                log(f"  [+] DataDome OK (retry): {new_dd[:45]}...")
                return new_dd

    # Fallback: Playwright
    if HAS_PLAYWRIGHT:
        log("  [*] Thu Playwright...")
        dd = get_datadome_cookie_playwright()
        if dd:
            save_dd_cache(dd)
            return dd

    # Fallback: cached cookie
    cached_dd = load_dd_cache()
    if cached_dd:
        log(f"  [*] Dung cached DataDome cookie")
        return cached_dd

    log("  [!] Khong lay duoc DataDome cookie")
    log("  [!] Can HAR file: python3 auto_danzhu.py game.har -a accounts.txt -c MA_MOI")
    return ""


def find_chromium_path():
    import shutil
    import glob as glob_mod
    pw_paths = glob_mod.glob("/opt/pw-browsers/chromium*/chrome-linux/chrome")
    if pw_paths:
        return pw_paths[0]
    for name in ["chromium", "chromium-browser", "google-chrome", "chrome"]:
        p = shutil.which(name)
        if p:
            return p
    return None


def get_datadome_cookie_playwright(timeout_sec=45):
    if not HAS_PLAYWRIGHT:
        return ""
    chrome_path = find_chromium_path()
    if not chrome_path:
        return ""
    log("  [*] Dang mo trinh duyet...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, executable_path=chrome_path,
                args=["--disable-blink-features=AutomationControlled",
                       "--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=BROWSER_UA,
                viewport={"width": 412, "height": 915},
                device_scale_factor=2.625, is_mobile=True, has_touch=True,
                locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh",
                ignore_https_errors=True,
            )
            context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>false});"
                "window.chrome={runtime:{}};"
            )
            page = context.new_page()

            validated = []
            dd_cookies = []

            def on_response(resp):
                try:
                    if resp.status == 200 and resp.request.method == "POST":
                        body = resp.text()
                        if '"cookie"' in body and "datadome=" in body:
                            data = json.loads(body)
                            val = data["cookie"].split("datadome=")[1].split(";")[0]
                            if data.get("view") == "redirect":
                                validated.append(val)
                            else:
                                dd_cookies.append(val)
                except Exception:
                    pass

            page.on("response", on_response)
            page.goto(OAUTH_URL, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if validated:
                    break
                page.wait_for_timeout(500)

            cookie_value = ""
            if validated:
                cookie_value = validated[-1]
            else:
                for c in context.cookies():
                    if c["name"] == "datadome":
                        cookie_value = c["value"]
                        break
                if not cookie_value and dd_cookies:
                    cookie_value = dd_cookies[-1]

            browser.close()
            if cookie_value:
                log(f"  [+] Playwright DataDome: {cookie_value[:40]}...")
            return cookie_value
    except Exception as e:
        log(f"  [!] Playwright loi: {e}")
        return ""


# ── GARENA AUTH ──────────────────────────────────────────────────────────────

def make_session(dd_cookie, template_cookies=None):
    """Tao requests.Session voi cookies tu HAR (fake browser state)."""
    if HAS_CURL_CFFI:
        session = curl_requests.Session(impersonate="chrome120")
    elif HAS_REQUESTS:
        session = std_requests.Session()
    else:
        raise RuntimeError("Can curl_cffi hoac requests")

    session.headers.update({
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
    })

    template_cookies = template_cookies or {}
    for name, val in template_cookies.items():
        if name == "datadome":
            val = dd_cookie or val
        domain = "100054.connect.garena.com" if "state" in name else ".garena.com"
        try:
            session.cookies.set(name, val, domain=domain, path="/")
        except Exception:
            session.cookies.set(name, val)

    if dd_cookie:
        try:
            session.cookies.set("datadome", dd_cookie, domain=".garena.com", path="/")
        except Exception:
            session.cookies.set("datadome", dd_cookie)

    return session


def garena_login(session, account, password):
    # Step 1: Prelogin
    prelogin_url = (
        f"{GARENA_CONNECT_BASE}/api/prelogin?"
        f"app_id={GARENA_APP_ID}"
        f"&account={urllib.parse.quote(account)}"
        f"&format=json&id={ts_ms()}"
    )
    resp = session.get(prelogin_url, timeout=15)

    if resp.status_code == 403:
        try:
            data = resp.json()
            if "url" in data and "captcha" in str(data.get("url", "")):
                return {"_captcha": True}
        except Exception:
            pass
        raise RuntimeError("Prelogin 403")

    resp.raise_for_status()
    prelogin_data = resp.json()
    v2 = prelogin_data.get("v2", "")
    if not v2:
        if "url" in prelogin_data and "captcha" in str(prelogin_data.get("url", "")):
            return {"_captcha": True}
        raise RuntimeError(f"Prelogin khong tra ve v2: {prelogin_data}")

    # Step 2: Login
    pw_hash = garena_password_hash(password)
    login_url = (
        f"{GARENA_CONNECT_BASE}/api/login?"
        f"app_id={GARENA_APP_ID}"
        f"&account={urllib.parse.quote(account)}"
        f"&password={pw_hash}"
        f"&redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&format=json&id={ts_ms()}"
    )
    resp = session.get(login_url, timeout=15)
    if resp.status_code == 403:
        raise RuntimeError("Login 403 - DataDome chan")
    resp.raise_for_status()
    login_data = resp.json()
    if "error" in login_data:
        raise RuntimeError(f"Login: {login_data.get('error')} - {login_data.get('error_description','')}")
    session_key = login_data.get("session_key", "")
    uid = login_data.get("uid", "")
    if not session_key:
        raise RuntimeError(f"Login khong co session_key: {login_data}")
    log(f"  [+] Garena login OK: uid={uid}")

    # Step 3: Token Grant
    grant_data = (
        f"client_id={GARENA_APP_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&login_scenario=normal&format=json&id={ts_ms()}"
    )
    resp = session.post(
        f"{GARENA_CONNECT_BASE}/oauth/token/grant",
        data=grant_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Origin": GARENA_CONNECT_BASE,
        },
        timeout=15,
    )
    resp.raise_for_status()
    code = resp.json().get("code", "")
    if not code:
        raise RuntimeError(f"Token grant khong co code: {resp.text[:200]}")

    # Step 4: Token Exchange
    exchange_data = (
        f"code={code}"
        f"&grant_type=authorization_code"
        f"&login_scenario=normal"
        f"&redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&source=2"
        f"&client_secret={GARENA_CLIENT_SECRET}"
        f"&client_id={GARENA_APP_ID}"
    )
    resp = do_request("POST", f"{GARENA_CONNECT_BASE}/oauth/token/exchange",
                      data=exchange_data, headers={
                          "User-Agent": SDK_UA,
                          "Content-Type": "application/x-www-form-urlencoded",
                      })
    resp.raise_for_status()
    exch = resp.json()
    if not exch.get("access_token"):
        raise RuntimeError(f"Token exchange loi: {resp.text[:200]}")
    log(f"  [+] Token exchange OK: open_id={exch['open_id'][:16]}...")

    return {
        "access_token": exch["access_token"],
        "open_id": exch["open_id"],
        "uid": exch.get("uid", ""),
    }


def full_login(username, password, dd, template_cookies, jspl_payload):
    """Login Garena voi tu dong refresh DataDome neu bi block."""
    for attempt in range(3):
        session = make_session(dd, template_cookies)
        try:
            result = garena_login(session, username, password)
        except Exception as e:
            log(f"  [!] Garena login loi: {e}")
            return None, dd

        if isinstance(result, dict) and result.get("_captcha"):
            if attempt < 2:
                log(f"  [!] DataDome blocked (lan {attempt+1}), lay cookie moi...")
                new_dd = fetch_datadome(dd, jspl_payload)
                if new_dd:
                    dd = new_dd
                    save_dd_cache(dd)
                    time.sleep(2)
                    continue
            log("  [!] Bi DataDome block - can HAR moi hoac --datadome cookie")
            return None, dd

        if isinstance(result, dict) and "access_token" in result:
            result["datadome"] = dd
            return result, dd

        return None, dd

    return None, dd


# ── ITOP LOGIN ───────────────────────────────────────────────────────────────

def itop_login(access_token, open_id):
    ts = str(int(time.time()))
    seq_id = f"{ITOP_GAMEID}-auto-{ts}"

    body = json.dumps({
        "openid": open_id, "token": access_token,
        "channelid": int(ITOP_CHANNELID), "gameid": int(ITOP_GAMEID),
        "os": 1, "lang": "", "seq": seq_id, "ts": ts,
    })

    params = (
        f"channelid={ITOP_CHANNELID}&encrypt=0&gameid={ITOP_GAMEID}"
        f"&lang=&os=1&seq={seq_id}&ts={ts}&version=null"
    )

    resp = do_request("POST", f"{ITOP_BASE}/v2/auth/login?{params}",
                      data=body, headers={
                          "Content-Type": "application/json",
                          "Host": "itop.kg.garena.vn",
                      })
    resp.raise_for_status()
    result = resp.json()
    if result.get("ret", -1) != 0:
        raise RuntimeError(f"ITOP loi: ret={result.get('ret')}, msg={result.get('msg','')}")

    ti = result.get("token_info", {})
    return {
        "aov_token": ti.get("aov_token", result.get("aov_token", "")),
        "game_openid": result.get("openid", ti.get("openid", "")),
        "game_token": ti.get("game_token", result.get("game_token", "")),
    }


# ── AOV EVENT API ────────────────────────────────────────────────────────────

def aov_headers(aov_token, game_openid, game_token):
    return {
        "Host": "aovcloud.garena.com",
        "User-Agent": UNITY_UA,
        "Accept": "*/*",
        "Content-Type": "application/json; charset=utf-8",
        "X-Unity-Version": "2022.3.5f1",
        "aov_token": aov_token,
        "GameOpenId": game_openid,
        "gameToken": game_token,
        "channel": "1", "platId": "1",
        "partition": AOV_PARTITION, "areaId": AOV_AREA_ID,
        "userinfo": json.dumps({
            "uin": game_openid, "areaID": AOV_AREA_ID,
            "roleID": game_openid, "platform": "1",
            "accType": "Guest", "partitionID": AOV_PARTITION,
        }, separators=(",", ":")),
        "lang": "VN", "version": "0.0.6",
        "gmTimeStamp": str(int(time.time())),
    }


def use_invitation_code(aov_token, game_openid, game_token, inv_code, usecode_path="danzhu"):
    url = f"{AOV_CLOUD_BASE}/vn_online/{usecode_path}/usecode"
    body = json.dumps({"invitationCode": inv_code})
    resp = do_request("POST", url, data=body,
                      headers=aov_headers(aov_token, game_openid, game_token))
    resp.raise_for_status()
    return resp.json()


def aov_startup(aov_token, game_openid, game_token, usecode_path="danzhu"):
    url = f"{AOV_CLOUD_BASE}/vn_online/{usecode_path}/getstartupdata"
    body = json.dumps({
        "deviceId": md5(game_openid),
        "lastLoginTime": 0, "name": "Player", "headUrl": "", "headFrameId": 0,
    })
    try:
        resp = do_request("POST", url, data=body,
                          headers=aov_headers(aov_token, game_openid, game_token))
        return resp.json()
    except Exception:
        return {}


# ── PROCESS: HAR SESSION (replay game tokens) ───────────────────────────────

def process_har_session(sess, inv_code, idx, total, usecode_path="danzhu"):
    uname = sess.get("username") or sess.get("GameOpenId", "???")
    goid = sess["GameOpenId"]
    gtok = sess["gameToken"]
    atok = sess["aov_token"]

    log(f"\n[{idx}/{total}] {uname} | GameOpenId={goid}")

    startup = aov_startup(atok, goid, gtok, usecode_path)
    scode = startup.get("code", -1)
    smsg = startup.get("msg", "")
    if scode == 0:
        log("  [+] Session OK")
    elif scode == 999 or "expired" in smsg.lower() or "token" in smsg.lower():
        log(f"  [!] aov_token het han: {smsg}")
        log("  [!] Can bat HAR moi (token chi song ~2h)")
        return "expired"
    else:
        log(f"  [*] startup code={scode}: {smsg}")

    time.sleep(1)
    log(f"  [*] usecode: {inv_code}")
    result = use_invitation_code(atok, goid, gtok, inv_code, usecode_path)
    if not result:
        return False

    code = result.get("code", -1)
    msg = result.get("msg", "")

    if code == 0:
        reward = result.get("rewardDanzhuNum", result.get("rewardTiliNum", 0))
        log(f"  [+] THANH CONG! +{reward}")
        own_code = result.get("inviteData", {}).get("invitationCode", "")
        if own_code:
            log(f"  [+] Ma moi cua acc nay: {own_code}")
        return True
    elif any(x in msg.lower() for x in ["already", "same"]) or code in (-3, -10, -11):
        log(f"  [!] Da dung ma nay roi (code={code}): {msg[:80]}")
        return None
    else:
        log(f"  [!] Loi code={code}: {msg[:100]}")
        return False


# ── PROCESS: LOGIN + USECODE ─────────────────────────────────────────────────

def process_account_login(username, password, inv_code, dd, template_cookies,
                          jspl_payload, delay, usecode_path="danzhu"):
    log(f"  [*] Dang nhap Garena: {username}...")
    tokens, dd = full_login(username, password, dd, template_cookies, jspl_payload)
    if not tokens:
        return False, dd

    time.sleep(delay)

    # ITOP login
    try:
        itop = itop_login(tokens["access_token"], tokens["open_id"])
        log(f"  [+] ITOP OK: GameOpenId={itop['game_openid']}")
    except Exception as e:
        log(f"  [!] ITOP THAT BAI: {e}")
        return False, dd

    time.sleep(delay)

    # Nhap ma
    try:
        result = use_invitation_code(
            itop["aov_token"], itop["game_openid"], itop["game_token"],
            inv_code, usecode_path,
        )
        code = result.get("code", -1)
        msg = result.get("msg", "")
        reward = result.get("rewardDanzhuNum", result.get("rewardTiliNum", 0))

        if code == 0:
            log(f"  [+] THANH CONG! +{reward}")
            own_code = result.get("inviteData", {}).get("invitationCode", "")
            if own_code:
                log(f"  [+] Ma moi cua acc nay: {own_code}")
            return True, dd
        else:
            log(f"  [!] Nhap ma that bai: code={code}, msg={msg}")
            return False, dd
    except Exception as e:
        log(f"  [!] Nhap ma loi: {e}")
        return False, dd


# ── LOAD ACCOUNTS ────────────────────────────────────────────────────────────

def load_accounts(filepath):
    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sep = "|" if "|" in line else ":"
            parts = [x.strip() for x in line.split(sep) if x.strip()]
            if len(parts) < 2:
                continue
            accounts.append({
                "username": parts[0],
                "password": parts[1],
                "aov_token": parts[2] if len(parts) > 2 else None,
                "game_openid": parts[3] if len(parts) > 3 else None,
                "game_token": parts[4] if len(parts) > 4 else None,
            })
    return accounts


def print_cookie_instructions():
    print("""
HUONG DAN LAY DATADOME COOKIE:

  1. Mo link sau trong trinh duyet:
     https://100054.connect.garena.com/universal/oauth?redirect_uri=gop100054%3A%2F%2Fauth%2F&response_type=code&client_id=100054&login_scenario=normal&locale=vi-VN

  2. Doi trang login hien ra (3-5 giay)

  3. Lay cookie:
     Chrome: F12 -> Application -> Cookies -> garena.com -> datadome
     Android: dung Kiwi Browser (co DevTools) hoac app Cookie Editor

  4. Chay tool:
     python3 auto_danzhu.py -a accounts.txt -c MA_MOI --datadome "COOKIE"

  HOAC tot hon: bat HAR bang HTTP Canary roi chay:
     python3 auto_danzhu.py game.har -a accounts.txt -c MA_MOI
""")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Auto nhap ma moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Vi du:
  # Dung HAR (tu dong DataDome, tot nhat):
  python3 auto_danzhu.py game.har -a accounts.txt -c MA_MOI

  # Replay session tu HAR:
  python3 auto_danzhu.py game.har -c MA_MOI

  # Thu cong:
  python3 auto_danzhu.py -a accounts.txt -c MA_MOI --datadome "COOKIE"
        """
    )
    parser.add_argument("har", nargs="?", default=None,
        help="HAR file (bat bang HTTP Canary)")
    parser.add_argument("--accounts", "-a",
        help="File tai khoan (account:password)")
    parser.add_argument("--code", "-c",
        help="Ma moi (invitationCode)")
    parser.add_argument("--delay", "-d", type=float, default=3.0,
        help="Delay giua cac buoc (giay)")
    parser.add_argument("--account-delay", type=float, default=5.0,
        help="Delay giua cac tai khoan (giay)")
    parser.add_argument("--datadome", default="",
        help="DataDome cookie thu cong")
    parser.add_argument("--get-cookie", action="store_true",
        help="Huong dan lay DataDome cookie")
    args = parser.parse_args()

    if args.get_cookie:
        if HAS_PLAYWRIGHT:
            log("[*] Dang thu lay cookie bang Playwright...")
            cookie = get_datadome_cookie_playwright(timeout_sec=45)
            if cookie:
                log(f"\n[+] THANH CONG! DataDome cookie:\n\n    {cookie}\n")
                log(f'[*] Dung: python3 auto_danzhu.py -a accounts.txt -c MA --datadome "{cookie}"')
                return
        print_cookie_instructions()
        return

    # Auto-detect: neu arg dau la .txt thi coi la accounts file
    if args.har and args.har.endswith(".txt") and not args.accounts:
        args.accounts = args.har
        args.har = None

    if not args.code:
        args.code = input("Nhap ma moi (invitationCode): ").strip()
    if not args.code:
        log("[!] Thieu ma moi!")
        sys.exit(1)

    # Parse HAR
    har_data = {"sessions": [], "template_cookies": {}, "datadome_cookie": "", "jspl_payload": ""}
    usecode_path = "danzhu"

    if args.har:
        if not os.path.exists(args.har):
            log(f"[!] Khong tim thay HAR: {args.har}")
            sys.exit(1)
        log(f"[*] Doc HAR: {args.har}...")
        har_data = parse_har(args.har)
        usecode_path = har_data.get("usecode_path", "danzhu")
        log(f"  [+] Tim thay {len(har_data['sessions'])} session trong HAR")
        log(f"  [+] jspl payload: {'co' if har_data['jspl_payload'] else 'khong'}")
        log(f"  [+] template cookies: {len(har_data['template_cookies'])} cookies")
        log(f"  [+] event endpoint: {usecode_path}/usecode")
        for s in har_data["sessions"]:
            log(f"      - {s.get('username') or s['GameOpenId']}")

    # Parse accounts
    accounts = []
    if args.accounts:
        accounts = load_accounts(args.accounts)
        log(f"[*] Tai khoan: {len(accounts)}")

    total = len(har_data["sessions"]) + len(accounts)
    if total == 0:
        log("[!] Khong co acc nao!")
        log("    Dung: python3 auto_danzhu.py game.har -a accounts.txt -c MA_MOI")
        sys.exit(1)

    log(f"[*] Ma moi: {args.code}")
    log(f"[*] HTTP: {'curl_cffi' if HAS_CURL_CFFI else 'requests'}")

    # Lay DataDome (1 lan cho toan bo batch)
    dd = ""
    if accounts:
        log("")
        dd = get_datadome(
            har_data["template_cookies"],
            har_data["jspl_payload"],
            args.datadome,
        )
    log("")

    ok = fail = skip = expired = 0
    job_idx = 0

    # Mode 1: Replay HAR sessions
    for sess in har_data["sessions"]:
        job_idx += 1
        res = process_har_session(sess, args.code, job_idx, total, usecode_path)
        if res is True:
            ok += 1
        elif res == "expired":
            expired += 1
        elif res is False:
            fail += 1
        else:
            skip += 1

        if job_idx < total:
            d = random.uniform(2.5, 5.0)
            time.sleep(d)

    # Mode 2: Login accounts
    for acc in accounts:
        job_idx += 1
        log(f"\n[{job_idx}/{total}] {acc['username']}")

        # Neu co game tokens trong file -> replay truc tiep
        if acc.get("aov_token") and acc.get("game_openid") and acc.get("game_token"):
            log("  [*] Dung game tokens co san")
            res = process_har_session({
                "username": acc["username"],
                "GameOpenId": acc["game_openid"],
                "gameToken": acc["game_token"],
                "aov_token": acc["aov_token"],
            }, args.code, job_idx, total, usecode_path)
            if res is True:
                ok += 1
            elif res == "expired":
                expired += 1
            elif res is False:
                fail += 1
            else:
                skip += 1
        else:
            # Login moi
            res, dd = process_account_login(
                acc["username"], acc["password"], args.code,
                dd, har_data["template_cookies"], har_data["jspl_payload"],
                args.delay, usecode_path,
            )
            if res is True:
                ok += 1
            else:
                fail += 1

        if job_idx < total:
            d = random.uniform(2.5, 5.0)
            time.sleep(d)

    # Ket qua
    log(f"\n{'='*50}")
    log(f"[*] Thanh cong:  {ok}")
    log(f"[*] Da dung/Skip: {skip}")
    if expired:
        log(f"[*] Token het han: {expired} (can HAR moi)")
    log(f"[*] That bai:    {fail}")
    log(f"[*] Tong:        {total}")
    log(f"[*] Log: {LOG_FILE}")
    log(f"{'='*50}")


if __name__ == "__main__":
    main()
