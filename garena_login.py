#!/usr/bin/env python3
"""
Garena Connect Login Module
Uses headless browser (puppeteer) to bypass DataDome protection.
Falls back to curl_cffi or curl if browser not available.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from urllib.parse import urlencode

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
    requests = None

GARENA_CONNECT_BASE = "https://100054.connect.garena.com"
APP_ID = "100054"
CLIENT_SECRET = "027709b12673a3e18de16bf9b85723a2d55e9bffd3364aea67f176e533f69515"
REDIRECT_URI = "gop100054://auth/"

WEB_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/149.0.7827.159 "
    "Mobile Safari/537.36"
)
SDK_USER_AGENT = "GarenaMSDK/4.0.38(SM-A165F ;Android 15;vi;VN;)"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_LOGIN_JS = os.path.join(SCRIPT_DIR, "garena_browser_login.js")


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


def _browser_login(account, password):
    """Login via headless browser (puppeteer). Bypasses DataDome."""
    if not os.path.exists(BROWSER_LOGIN_JS):
        return None

    # Check node
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=5)
    except Exception:
        return None

    try:
        result = subprocess.run(
            ["node", BROWSER_LOGIN_JS, account, password],
            capture_output=True, text=True, timeout=60,
            cwd=SCRIPT_DIR,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if not stdout:
            if stderr:
                print("  [browser] stderr: {}".format(stderr[:200]), file=sys.stderr)
            return None

        data = json.loads(stdout)

        if "error" in data:
            detail = data.get("detail", data.get("fix", ""))
            raise Exception("Browser login: {} — {}".format(data["error"], detail))

        if data.get("access_token"):
            return data

        if data.get("partial") and data.get("session_key"):
            print("  [browser] Partial login — co session_key nhung thieu OAuth token",
                  file=sys.stderr)
            return None

        return None

    except json.JSONDecodeError:
        return None
    except subprocess.TimeoutExpired:
        raise Exception("Browser login timeout (60s)")


def _curl_get_with_cookies(url, params=None, headers=None, cookies=None, timeout=15):
    """Simple curl GET with cookie support."""
    if params:
        url = url + "?" + urlencode(params)
    cmd = ["curl", "-s", "-L", "--compressed", "--max-time", str(timeout)]
    if headers:
        for k, v in headers.items():
            cmd.extend(["-H", "{}: {}".format(k, v)])
    if cookies:
        cmd.extend(["-b", cookies])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    if not result.stdout.strip():
        raise Exception("Empty response: {}".format(url[:80]))
    return json.loads(result.stdout)


def _curl_post_with_cookies(url, data=None, headers=None, cookies=None, timeout=15):
    """Simple curl POST with cookie support."""
    cmd = ["curl", "-s", "-L", "--compressed", "--max-time", str(timeout), "-X", "POST"]
    if headers:
        for k, v in headers.items():
            cmd.extend(["-H", "{}: {}".format(k, v)])
    if cookies:
        cmd.extend(["-b", cookies])
    if data:
        cmd.extend(["-d", urlencode(data) if isinstance(data, dict) else str(data)])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    if not result.stdout.strip():
        raise Exception("Empty response: {}".format(url[:80]))
    return json.loads(result.stdout)


def garena_login(account, password, session=None):
    """Full Garena login flow. Uses browser to bypass DataDome."""

    # Method 1: Browser-based login (bypasses DataDome)
    try:
        result = _browser_login(account, password)
        if result and result.get("access_token"):
            return result
    except Exception as e:
        err_msg = str(e)
        if "puppeteer not installed" in err_msg:
            print("  [!] Cai puppeteer: npm install puppeteer-core", file=sys.stderr)
        elif "chromium not found" in err_msg:
            print("  [!] Cai chromium: pkg install chromium", file=sys.stderr)
        else:
            print("  [!] Browser login loi: {}".format(err_msg[:100]), file=sys.stderr)

    # Method 2: Direct API (may be blocked by DataDome)
    print("  [!] Thu truc tiep API (co the bi DataDome chan)...", file=sys.stderr)
    return _direct_api_login(account, password, session)


def _direct_api_login(account, password, session=None):
    """Direct API login — works when DataDome is not active."""
    hdrs = {"User-Agent": WEB_USER_AGENT}
    ts = str(int(time.time() * 1000))

    try:
        use_requests = requests is not None
        if use_requests:
            s = session or requests.Session()
            resp = s.get(
                GARENA_CONNECT_BASE + "/api/prelogin",
                params={"app_id": APP_ID, "account": account,
                        "format": "json", "id": ts},
                headers=hdrs, timeout=15,
            )
            pre = resp.json()
        else:
            pre = _curl_get_with_cookies(
                GARENA_CONNECT_BASE + "/api/prelogin",
                params={"app_id": APP_ID, "account": account,
                        "format": "json", "id": ts},
                headers=hdrs,
            )
    except Exception as e:
        raise Exception("prelogin request failed: {}".format(str(e)[:100]))

    # Check for DataDome
    if isinstance(pre, dict) and "url" in pre and "v1" not in pre:
        u = pre.get("url", "")
        if "captcha" in u or "datadome" in u:
            raise Exception(
                "DataDome chan! Can cai:\n"
                "  npm install puppeteer-core\n"
                "  pkg install chromium  (Termux)\n"
                "Roi chay lai.")
        raise Exception("prelogin redirect: {}".format(u[:150]))

    if "v1" not in pre or "v2" not in pre:
        raise Exception("prelogin failed: {}".format(json.dumps(pre)[:200]))

    v1, v2 = pre["v1"], pre["v2"]
    ts2 = str(int(time.time() * 1000))
    encrypted_pw = hash_password(password, v1, v2)

    login_params = {
        "app_id": APP_ID, "account": account,
        "password": encrypted_pw, "redirect_uri": REDIRECT_URI,
        "format": "json", "id": ts2,
    }

    if use_requests:
        resp2 = s.get(GARENA_CONNECT_BASE + "/api/login",
                      params=login_params, headers=hdrs, timeout=15)
        login_data = resp2.json()
    else:
        login_data = _curl_get_with_cookies(
            GARENA_CONNECT_BASE + "/api/login",
            params=login_params, headers=hdrs)

    if "error" in login_data:
        raise Exception("login failed: {}".format(login_data["error"]))
    if "session_key" not in login_data:
        raise Exception("no session_key: {}".format(json.dumps(login_data)[:200]))

    session_key = login_data["session_key"]
    garena_uid = login_data.get("uid")

    ts3 = str(int(time.time() * 1000))
    grant_payload = {
        "client_id": APP_ID, "response_type": "code",
        "redirect_uri": REDIRECT_URI, "login_scenario": "normal",
        "format": "json", "id": ts3,
    }
    grant_hdrs = {"User-Agent": WEB_USER_AGENT,
                  "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"}

    if use_requests:
        resp3 = s.post(GARENA_CONNECT_BASE + "/oauth/token/grant",
                       data=grant_payload, headers=grant_hdrs, timeout=15)
        grant_data = resp3.json()
    else:
        grant_data = _curl_post_with_cookies(
            GARENA_CONNECT_BASE + "/oauth/token/grant",
            data=grant_payload, headers=grant_hdrs)

    if "code" not in grant_data:
        raise Exception("token/grant failed: {}".format(json.dumps(grant_data)[:200]))

    oauth_code = grant_data["code"]
    open_id = grant_data.get("open_id", "")
    platform_uid = grant_data.get("uid")

    exchange_payload = {
        "code": oauth_code, "grant_type": "authorization_code",
        "login_scenario": "normal", "redirect_uri": REDIRECT_URI,
        "source": "2", "client_secret": CLIENT_SECRET, "client_id": APP_ID,
    }
    exchange_hdrs = {"User-Agent": SDK_USER_AGENT,
                     "Content-Type": "application/x-www-form-urlencoded"}

    if use_requests:
        resp4 = s.post(GARENA_CONNECT_BASE + "/oauth/token/exchange",
                       data=exchange_payload, headers=exchange_hdrs, timeout=15)
        exchange_data = resp4.json()
    else:
        exchange_data = _curl_post_with_cookies(
            GARENA_CONNECT_BASE + "/oauth/token/exchange",
            data=exchange_payload, headers=exchange_hdrs)

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
    }


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
            if requests:
                s = session or requests.Session()
                resp = s.post(endpoint, data=post_data,
                              headers=post_hdrs, timeout=15)
                data = resp.json()
            else:
                data = _curl_post_with_cookies(
                    endpoint, data=post_data, headers=post_hdrs)
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


def get_msdk_auth_token(account, password):
    login_result = garena_login(account, password)
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
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python garena_login.py <account> <password>")
        sys.exit(1)

    print("[*] Logging in as {}...".format(sys.argv[1]))
    try:
        result = garena_login(sys.argv[1], sys.argv[2])
        print("[+] Login OK!")
        print("  uid:          {}".format(result["uid"]))
        print("  open_id:      {}".format(result["open_id"]))
        print("  access_token: {}...".format(result["access_token"][:30]))
        print("  session_key:  {}...".format(result["session_key"][:30]))
        print("  expires_in:   {}s".format(result["expires_in"]))
    except Exception as e:
        print("[-] Failed: {}".format(e))
        sys.exit(1)
