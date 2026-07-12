#!/usr/bin/env python3
"""
Garena Connect Login Module
Bypass DataDome bằng cách replay jspl payload từ HAR.
Flow: HAR → extract jspl + cookies → POST datadome.garena.com/js/
      → lấy datadome cookie → dùng cookie login API bình thường.
"""

import hashlib
import json
import os
import re
import sys
import time

try:
    from Crypto.Cipher import AES
except ImportError:
    try:
        from Cryptodome.Cipher import AES
    except ImportError:
        AES = None

try:
    import requests
except ImportError:
    print("\033[91m[!] pip install requests\033[0m")
    sys.exit(1)

GARENA_CONNECT_BASE = "https://100054.connect.garena.com"
APP_ID = "100054"
CLIENT_SECRET = "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515"
REDIRECT_URI = "gop100054://auth/"
DD_KEY = "AE3F04AD3F0D3A462481A337485081"

WEB_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/149.0.7827.159 "
    "Mobile Safari/537.36"
)
SDK_USER_AGENT = "GarenaMSDK/4.0.38(SM-A165F ;Android 15;vi;VN;)"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HAR_CACHE_FILE = os.path.join(SCRIPT_DIR, ".har_cache.json")
DD_CACHE_FILE = os.path.join(SCRIPT_DIR, ".dd_cookie")


# ─── DATADOME ────────────────────────────────────────────────────────────────

def parse_har_datadome(har_path):
    """Extract jspl payload + template cookies from HAR file."""
    with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
        har = json.load(f)
    entries = har["log"]["entries"]

    result = {"jspl_payload": "", "template_cookies": {}}

    # Template cookies from first prelogin request
    for e in entries:
        if "api/prelogin" in e["request"]["url"]:
            cookies = {c["name"]: c["value"]
                       for c in e["request"].get("cookies", [])}
            result["template_cookies"] = cookies
            break

    # jspl payload from datadome POST
    for e in entries:
        url = e["request"]["url"]
        if ("datadome.garena.com/js/" in url
                and e["request"]["method"] == "POST"):
            body = e["request"].get("postData", {}).get("text", "")
            if "jspl=" in body:
                result["jspl_payload"] = body
                break

    return result


def save_har_cache(jspl_payload, template_cookies):
    try:
        with open(HAR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"jspl_payload": jspl_payload,
                       "template_cookies": template_cookies}, f)
    except Exception:
        pass


def load_har_cache():
    if os.path.exists(HAR_CACHE_FILE):
        try:
            with open(HAR_CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_dd_cookie():
    if os.path.exists(DD_CACHE_FILE):
        try:
            with open(DD_CACHE_FILE) as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def save_dd_cookie(val):
    try:
        with open(DD_CACHE_FILE, "w") as f:
            f.write(val)
    except Exception:
        pass


def fetch_datadome(current_dd="", jspl_payload=""):
    """POST jspl to datadome.garena.com/js/ → fresh datadome cookie."""
    url = "https://datadome.garena.com/js/"
    hdrs = {
        "User-Agent": WEB_USER_AGENT,
        "sec-ch-ua": '"Android WebView";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
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
            r'cid=[^&]*',
            'cid={}'.format(requests.utils.quote(current_dd)),
            jspl_payload)
    else:
        payload = (
            "jspl=placeholder&eventCounters=%7B%7D&jsType=le"
            "&cid={}&ddk={}".format(
                requests.utils.quote(current_dd), DD_KEY)
            + "&Referer=https%3A%2F%2F100054.connect.garena.com%2F"
              "&request=%2Funiversal%2Foauth&responsePage=origin&ddv=5.8.0"
        )

    try:
        r = requests.post(url, headers=hdrs, data=payload, timeout=15)
        data = r.json()
        if data.get("status") == 200 and "cookie" in data:
            m = re.search(r'datadome=([^;]+)', data["cookie"])
            if m:
                return m.group(1)
    except Exception:
        pass
    return ""


def get_datadome(template_cookies=None, jspl_payload=""):
    """Get a valid datadome cookie. Try cache, then fetch new."""
    if template_cookies is None:
        template_cookies = {}

    # Load cached jspl if not provided
    if not jspl_payload:
        cached = load_har_cache()
        jspl_payload = cached.get("jspl_payload", "")
        if not template_cookies and cached.get("template_cookies"):
            template_cookies = cached["template_cookies"]

    if not jspl_payload:
        return "", template_cookies

    current_dd = template_cookies.get("datadome", "") or load_dd_cookie()

    # Try with current cookie
    new_dd = fetch_datadome(current_dd, jspl_payload)
    if new_dd:
        save_dd_cookie(new_dd)
        return new_dd, template_cookies

    # Retry with empty cid
    if current_dd:
        new_dd = fetch_datadome("", jspl_payload)
        if new_dd:
            save_dd_cookie(new_dd)
            return new_dd, template_cookies

    # Use cached if available
    if current_dd:
        return current_dd, template_cookies

    return "", template_cookies


def make_garena_session(dd_cookie, template_cookies=None):
    """Create requests.Session with DataDome + template cookies."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": WEB_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "sec-ch-ua": '"Android WebView";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "X-Requested-With": "com.garena.game.kgvn",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": (
            "https://100054.connect.garena.com/universal/oauth?"
            "redirect_uri=gop100054://auth/&response_type=code"
            "&client_id=100054&login_scenario=normal&locale=vi-VN"
        ),
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
    })

    # Set template cookies (browser state from HAR)
    if template_cookies:
        for name, val in template_cookies.items():
            if name == "datadome":
                val = dd_cookie
            domain = ("100054.connect.garena.com"
                      if "state" in name else ".garena.com")
            c = requests.cookies.create_cookie(
                name, val, domain=domain, path="/")
            s.cookies.set_cookie(c)

    # Ensure datadome cookie on .garena.com
    if dd_cookie:
        c = requests.cookies.create_cookie(
            "datadome", dd_cookie, domain=".garena.com", path="/")
        s.cookies.set_cookie(c)

    return s


# ─── PASSWORD HASHING ────────────────────────────────────────────────────────

def _aes_ecb_encrypt_no_padding(plaintext_bytes, key_bytes):
    if AES is not None:
        cipher = AES.new(key_bytes, AES.MODE_ECB)
        return cipher.encrypt(plaintext_bytes)
    raise ImportError("pip install pycryptodome")


def hash_password(password, v1, v2):
    md5_hex = hashlib.md5(password.encode()).hexdigest()
    sha_inner = hashlib.sha256((md5_hex + v1).encode()).hexdigest()
    sha_key = hashlib.sha256((sha_inner + v2).encode()).digest()
    md5_bytes = bytes.fromhex(md5_hex)
    encrypted = _aes_ecb_encrypt_no_padding(md5_bytes, sha_key)
    return encrypted.hex()


# ─── LOGIN FLOW ──────────────────────────────────────────────────────────────

def garena_login(account, password, dd_cookie="", template_cookies=None,
                 jspl_payload="", har_path=None):
    """Full Garena login flow with DataDome bypass.

    First run: provide har_path to extract jspl + cookies (cached for later).
    Subsequent runs: uses cached jspl/cookies automatically.
    """
    # Parse HAR if provided
    if har_path:
        har_data = parse_har_datadome(har_path)
        jspl_payload = har_data["jspl_payload"]
        template_cookies = har_data["template_cookies"]
        save_har_cache(jspl_payload, template_cookies)

    # Get DataDome cookie
    if not dd_cookie:
        dd_cookie, template_cookies = get_datadome(
            template_cookies, jspl_payload)

    if not dd_cookie:
        raise Exception(
            "Khong lay duoc DataDome cookie!\n"
            "  Can chay 1 lan voi HAR: python auto_loadtran.py --har game.har\n"
            "  Hoac copy file .har_cache.json + .dd_cookie tu may co HAR.")

    # Login with retry on DataDome block
    for attempt in range(3):
        s = make_garena_session(dd_cookie, template_cookies)

        # Step 1: prelogin
        ts = str(int(time.time() * 1000))
        resp = s.get(
            GARENA_CONNECT_BASE + "/api/prelogin",
            params={"app_id": APP_ID, "account": account,
                    "format": "json", "id": ts},
            timeout=15,
        )
        pre = resp.json()

        # Check DataDome block
        if "url" in pre and "v1" not in pre:
            u = pre.get("url", "")
            if "captcha" in u or "datadome" in u:
                if attempt < 2:
                    new_dd = fetch_datadome(dd_cookie, jspl_payload)
                    if new_dd:
                        dd_cookie = new_dd
                        save_dd_cookie(dd_cookie)
                        time.sleep(2)
                        continue
                raise Exception(
                    "DataDome van chan sau {} lan thu!\n"
                    "  Can HAR moi: bat HTTP Canary → mo game → login → export HAR\n"
                    "  Roi chay: python auto_loadtran.py --har game.har".format(
                        attempt + 1))
            raise Exception("prelogin redirect: {}".format(u[:150]))

        if "v1" not in pre or "v2" not in pre:
            raise Exception("prelogin failed: {}".format(
                json.dumps(pre)[:200]))

        v1, v2 = pre["v1"], pre["v2"]

        # Step 2: login
        ts2 = str(int(time.time() * 1000))
        encrypted_pw = hash_password(password, v1, v2)
        resp2 = s.get(
            GARENA_CONNECT_BASE + "/api/login",
            params={
                "app_id": APP_ID, "account": account,
                "password": encrypted_pw,
                "redirect_uri": REDIRECT_URI,
                "format": "json", "id": ts2,
            },
            timeout=15,
        )
        login_data = resp2.json()

        if "error" in login_data:
            raise Exception("login failed: {}".format(
                login_data.get("error_description", login_data["error"])))
        if "session_key" not in login_data:
            raise Exception("no session_key: {}".format(
                json.dumps(login_data)[:200]))

        session_key = login_data["session_key"]
        garena_uid = login_data.get("uid")

        # Step 3: token/grant
        ts3 = str(int(time.time() * 1000))
        resp3 = s.post(
            GARENA_CONNECT_BASE + "/oauth/token/grant",
            data={
                "client_id": APP_ID, "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "login_scenario": "normal",
                "format": "json", "id": ts3,
            },
            timeout=15,
        )
        grant_data = resp3.json()

        if "code" not in grant_data:
            raise Exception("token/grant failed: {}".format(
                json.dumps(grant_data)[:200]))

        oauth_code = grant_data["code"]
        open_id = grant_data.get("open_id", "")
        platform_uid = grant_data.get("uid")

        # Step 4: token/exchange (no session cookies needed)
        resp4 = requests.post(
            GARENA_CONNECT_BASE + "/oauth/token/exchange",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": SDK_USER_AGENT,
            },
            data={
                "code": oauth_code,
                "grant_type": "authorization_code",
                "login_scenario": "normal",
                "redirect_uri": REDIRECT_URI,
                "source": "2",
                "client_secret": CLIENT_SECRET,
                "client_id": APP_ID,
            },
            timeout=15,
        )
        exchange_data = resp4.json()

        if "access_token" not in exchange_data:
            raise Exception("token/exchange failed: {}".format(
                json.dumps(exchange_data)[:200]))

        return {
            "uid": exchange_data.get("uid", platform_uid),
            "garena_uid": garena_uid,
            "open_id": exchange_data.get("open_id", open_id),
            "access_token": exchange_data["access_token"],
            "refresh_token": exchange_data.get("refresh_token", ""),
            "session_key": session_key,
            "expiry_time": exchange_data.get("expiry_time", 0),
            "expires_in": exchange_data.get("expires_in", 0),
            "platform": exchange_data.get("platform", 3),
            "datadome": dd_cookie,
        }

    raise Exception("Login failed after retries")


# ─── MSDK TOKEN ──────────────────────────────────────────────────────────────

def build_itopencodeparam(open_id, access_token):
    token_str = "{}|{}".format(open_id, access_token)
    token_bytes = token_str.encode("utf-8")
    pad_len = 16 - (len(token_bytes) % 16)
    if pad_len < 16:
        token_bytes += bytes([pad_len] * pad_len)
    key = hashlib.md5(CLIENT_SECRET.encode()).digest()
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(token_bytes)
    return encrypted.hex().upper()


def build_itopencodeparam_raw(open_id, access_token):
    combined = open_id.encode("utf-8") + b"|" + access_token.encode("utf-8")
    return combined.hex().upper()


def try_itop_login(open_id, access_token, uid, session=None):
    endpoints = [
        "https://itop.kg.garena.vn/auth/login_garena",
        "https://itop.kg.garena.vn/v2/auth/login_garena",
        "https://itop.kg.garena.vn/auth/login",
    ]
    post_data = {
        "gameid": "1137", "channelid": "10",
        "openid": open_id, "token": access_token,
        "uid": str(uid), "os": "1", "lang": "vi", "area": "VN",
    }
    post_hdrs = {"User-Agent": SDK_USER_AGENT,
                 "Content-Type": "application/x-www-form-urlencoded"}
    for endpoint in endpoints:
        try:
            resp = requests.post(endpoint, data=post_data,
                                 headers=post_hdrs, timeout=15)
            data = resp.json()
            if data.get("ret") == 0:
                itop_openid = data.get("openid", "")
                itop_token = data.get("token", "")
                if itop_openid and itop_token:
                    return (itop_openid + itop_token).upper()
                encodeparam = data.get("itopencodeparam", "")
                if encodeparam:
                    return encodeparam
        except Exception:
            continue
    return None


def get_msdk_auth_token(account, password, har_path=None):
    login_result = garena_login(account, password, har_path=har_path)
    open_id = login_result["open_id"]
    access_token = login_result["access_token"]
    uid = login_result["uid"]
    itop_token = try_itop_login(open_id, access_token, uid)
    if not itop_token:
        itop_token = build_itopencodeparam_raw(open_id, access_token)
    return {
        "itopencodeparam": itop_token,
        "open_id": open_id,
        "access_token": access_token,
        "uid": uid,
        "session_key": login_result["session_key"],
        "garena_uid": login_result.get("garena_uid"),
        "datadome": login_result.get("datadome", ""),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python garena_login.py <account> <password> [har_file]")
        sys.exit(1)

    account = sys.argv[1]
    password = sys.argv[2]
    har = sys.argv[3] if len(sys.argv) > 3 else None

    print("[*] Logging in as {}...".format(account))
    try:
        result = garena_login(account, password, har_path=har)
        print("[+] Login OK!")
        print("  uid:          {}".format(result["uid"]))
        print("  open_id:      {}".format(result["open_id"]))
        print("  access_token: {}...".format(result["access_token"][:30]))
        print("  session_key:  {}...".format(result["session_key"][:30]))
        print("  expires_in:   {}s".format(result["expires_in"]))
    except Exception as e:
        print("[-] Failed: {}".format(e))
        sys.exit(1)
