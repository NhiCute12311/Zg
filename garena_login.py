#!/usr/bin/env python3
"""
Garena Connect Login Module
Automates the Garena authentication flow:
  1. prelogin  → get v1 (salt), v2 (random key)
  2. login     → AES-ECB encrypted password → session_key
  3. OAuth grant → authorization code
  4. OAuth exchange → access_token, open_id, uid

Uses curl_cffi (Chrome TLS impersonation) to bypass DataDome.
Fallback: subprocess curl with browser headers.
"""

import hashlib
import json
import subprocess
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

# Try curl_cffi for Chrome TLS impersonation (best DataDome bypass)
try:
    from curl_cffi import requests as cffi_requests
    _HAS_CFFI = True
except ImportError:
    _HAS_CFFI = False

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

_BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "sec-ch-ua": '"Chromium";v="149", "Not=A?Brand";v="8"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
}


class _HttpClient:
    """HTTP client with DataDome bypass. Tries curl_cffi → curl → requests."""

    def __init__(self):
        self._session = None
        self._cookie_jar = None
        self._method = None

    def _init_cffi(self):
        self._session = cffi_requests.Session(impersonate="chrome120")
        self._method = "cffi"

    def _init_curl(self):
        import tempfile
        self._cookie_jar = tempfile.mktemp(suffix=".txt")
        self._method = "curl"

    def _ensure_init(self):
        if self._method:
            return
        if _HAS_CFFI:
            self._init_cffi()
        else:
            self._init_curl()

    def get(self, url, params=None, headers=None, timeout=15):
        self._ensure_init()
        if self._method == "cffi":
            return self._cffi_get(url, params, headers, timeout)
        return self._curl_get(url, params, headers, timeout)

    def post(self, url, data=None, headers=None, timeout=15):
        self._ensure_init()
        if self._method == "cffi":
            return self._cffi_post(url, data, headers, timeout)
        return self._curl_post(url, data, headers, timeout)

    def _cffi_get(self, url, params, headers, timeout):
        h = dict(_BROWSER_HEADERS)
        if headers:
            h.update(headers)
        resp = self._session.get(url, params=params, headers=h, timeout=timeout)
        return self._parse(resp.text, url)

    def _cffi_post(self, url, data, headers, timeout):
        h = dict(_BROWSER_HEADERS)
        if headers:
            h.update(headers)
        resp = self._session.post(url, data=data, headers=h, timeout=timeout)
        return self._parse(resp.text, url)

    def _curl_get(self, url, params, headers, timeout):
        if params:
            url = url + "?" + urlencode(params)
        cmd = self._curl_base(timeout)
        h = dict(_BROWSER_HEADERS)
        if headers:
            h.update(headers)
        for k, v in h.items():
            cmd.extend(["-H", "{}: {}".format(k, v)])
        cmd.append(url)
        return self._run_curl(cmd, timeout, url)

    def _curl_post(self, url, data, headers, timeout):
        cmd = self._curl_base(timeout)
        cmd.extend(["-X", "POST"])
        h = dict(_BROWSER_HEADERS)
        if headers:
            h.update(headers)
        for k, v in h.items():
            cmd.extend(["-H", "{}: {}".format(k, v)])
        if data:
            if isinstance(data, dict):
                cmd.extend(["-d", urlencode(data)])
            else:
                cmd.extend(["-d", str(data)])
        cmd.append(url)
        return self._run_curl(cmd, timeout, url)

    def _curl_base(self, timeout):
        return [
            "curl", "-s", "-L", "--compressed",
            "--max-time", str(timeout),
            "--http2",
            "-b", self._cookie_jar,
            "-c", self._cookie_jar,
        ]

    def _run_curl(self, cmd, timeout, url):
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 10)
        return self._parse(result.stdout, url)

    def _parse(self, body, url):
        if not body or not body.strip():
            raise Exception("Empty response: {}".format(url[:80]))
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise Exception("Non-JSON ({}): {}".format(url[:50], body[:200]))
        if isinstance(data, dict) and "url" in data and "v1" not in data:
            u = data["url"]
            if "captcha" in u or "datadome" in u or "geo.captcha" in u:
                raise Exception(
                    "DataDome CAPTCHA detected! "
                    "Can: pip install curl_cffi" if not _HAS_CFFI else
                    "DataDome van chan. Thu VPN/doi mang.")
        return data


_http = _HttpClient()


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


def garena_login(account, password, session=None):
    """Full Garena login flow. Returns dict with uid, open_id, access_token, etc."""
    ts = str(int(time.time() * 1000))
    hdrs = {"User-Agent": WEB_USER_AGENT}

    # Step 1: prelogin
    pre = _http.get(
        GARENA_CONNECT_BASE + "/api/prelogin",
        params={
            "app_id": APP_ID,
            "account": account,
            "format": "json",
            "id": ts,
        },
        headers=hdrs,
    )

    if "v1" not in pre or "v2" not in pre:
        raise Exception("prelogin failed: {}".format(json.dumps(pre)[:200]))

    v1 = pre["v1"]
    v2 = pre["v2"]

    # Step 2: login with encrypted password
    ts2 = str(int(time.time() * 1000))
    encrypted_pw = hash_password(password, v1, v2)
    login_data = _http.get(
        GARENA_CONNECT_BASE + "/api/login",
        params={
            "app_id": APP_ID,
            "account": account,
            "password": encrypted_pw,
            "redirect_uri": REDIRECT_URI,
            "format": "json",
            "id": ts2,
        },
        headers=hdrs,
    )

    if "error" in login_data:
        raise Exception("login failed: {}".format(login_data["error"]))
    if "session_key" not in login_data:
        raise Exception("login: no session_key: {}".format(
            json.dumps(login_data)[:200]))

    session_key = login_data["session_key"]
    garena_uid = login_data.get("uid")

    # Step 3: OAuth token/grant
    ts3 = str(int(time.time() * 1000))
    grant_data = _http.post(
        GARENA_CONNECT_BASE + "/oauth/token/grant",
        data={
            "client_id": APP_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "login_scenario": "normal",
            "format": "json",
            "id": ts3,
        },
        headers={
            "User-Agent": WEB_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
    )

    if "code" not in grant_data:
        raise Exception("token/grant failed: {}".format(
            json.dumps(grant_data)[:200]))

    oauth_code = grant_data["code"]
    open_id = grant_data.get("open_id", "")
    platform_uid = grant_data.get("uid")

    # Step 4: OAuth token/exchange
    exchange_data = _http.post(
        GARENA_CONNECT_BASE + "/oauth/token/exchange",
        data={
            "code": oauth_code,
            "grant_type": "authorization_code",
            "login_scenario": "normal",
            "redirect_uri": REDIRECT_URI,
            "source": "2",
            "client_secret": CLIENT_SECRET,
            "client_id": APP_ID,
        },
        headers={
            "User-Agent": SDK_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

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
        "gameid": "1137",
        "channelid": "10",
        "openid": open_id,
        "token": access_token,
        "uid": str(uid),
        "os": "1",
        "lang": "vi",
        "area": "VN",
    }
    post_hdrs = {
        "User-Agent": SDK_USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    for endpoint in endpoints:
        try:
            data = _http.post(endpoint, data=post_data, headers=post_hdrs)
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
    import sys
    if len(sys.argv) < 3:
        print("Usage: python garena_login.py <account> <password>")
        sys.exit(1)

    print("[*] HTTP method: {}".format(
        "curl_cffi (Chrome)" if _HAS_CFFI else "curl subprocess"))
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
