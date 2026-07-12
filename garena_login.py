#!/usr/bin/env python3
"""
Garena Connect Login Module
Automates the Garena authentication flow:
  1. prelogin  → get v1 (salt), v2 (random key)
  2. login     → AES-ECB encrypted password → session_key
  3. OAuth grant → authorization code
  4. OAuth exchange → access_token, open_id, uid
"""

import hashlib
import json
import time
import struct

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


def _aes_ecb_encrypt_no_padding(plaintext_bytes, key_bytes):
    if AES is not None:
        cipher = AES.new(key_bytes, AES.MODE_ECB)
        return cipher.encrypt(plaintext_bytes)
    raise ImportError("pip install pycryptodome")


def hash_password(password, v1, v2):
    """Hash password using Garena's algorithm:
    1. r = MD5(password) → hex string
    2. S = SHA256(SHA256(r + v1) + v2) → 32 bytes key
    3. AES-ECB-NoPadding encrypt r_bytes with S
    """
    md5_hex = hashlib.md5(password.encode()).hexdigest()
    sha_inner = hashlib.sha256((md5_hex + v1).encode()).hexdigest()
    sha_key = hashlib.sha256((sha_inner + v2).encode()).digest()
    md5_bytes = bytes.fromhex(md5_hex)
    encrypted = _aes_ecb_encrypt_no_padding(md5_bytes, sha_key)
    return encrypted.hex()


def garena_login(account, password, session=None):
    """Full Garena login flow.

    Returns dict with keys:
        uid, open_id, access_token, session_key, refresh_token, expiry_time
    or raises Exception on failure.
    """
    if requests is None:
        raise ImportError("pip install requests")

    s = session or requests.Session()
    ts = str(int(time.time() * 1000))

    # Step 1: prelogin
    resp = s.get(
        GARENA_CONNECT_BASE + "/api/prelogin",
        params={
            "app_id": APP_ID,
            "account": account,
            "format": "json",
            "id": ts,
        },
        headers={"User-Agent": WEB_USER_AGENT},
        timeout=15,
    )
    pre = resp.json()
    if "v1" not in pre or "v2" not in pre:
        raise Exception("prelogin failed: {}".format(json.dumps(pre)[:200]))

    v1 = pre["v1"]
    v2 = pre["v2"]

    # Step 2: login with encrypted password
    ts2 = str(int(time.time() * 1000))
    encrypted_pw = hash_password(password, v1, v2)
    resp2 = s.get(
        GARENA_CONNECT_BASE + "/api/login",
        params={
            "app_id": APP_ID,
            "account": account,
            "password": encrypted_pw,
            "redirect_uri": REDIRECT_URI,
            "format": "json",
            "id": ts2,
        },
        headers={"User-Agent": WEB_USER_AGENT},
        timeout=15,
    )
    login_data = resp2.json()
    if "error" in login_data:
        raise Exception("login failed: {}".format(login_data["error"]))
    if "session_key" not in login_data:
        raise Exception("login: no session_key: {}".format(
            json.dumps(login_data)[:200]))

    session_key = login_data["session_key"]
    garena_uid = login_data.get("uid")

    # Step 3: OAuth token/grant
    ts3 = str(int(time.time() * 1000))
    resp3 = s.post(
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
        timeout=15,
    )
    grant_data = resp3.json()
    if "code" not in grant_data:
        raise Exception("token/grant failed: {}".format(
            json.dumps(grant_data)[:200]))

    oauth_code = grant_data["code"]
    open_id = grant_data.get("open_id", "")
    platform_uid = grant_data.get("uid")

    # Step 4: OAuth token/exchange
    resp4 = s.post(
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
    }


def build_itopencodeparam(open_id, access_token):
    """Build msdk-itopencodeparam from Garena credentials.

    The itopencodeparam is a hex-encoded structure containing the
    openid and token for MSDK authentication. For Garena channel (10),
    the format is the Garena open_id + access_token encoded.
    """
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
    """Build msdk-itopencodeparam using raw hex concatenation.

    Alternative encoding: hex(openid_bytes + token_bytes).
    """
    combined = open_id.encode("utf-8") + b"|" + access_token.encode("utf-8")
    return combined.hex().upper()


def try_itop_login(open_id, access_token, uid, session=None):
    """Try to authenticate with iTop to get MSDK credentials.

    Attempts known iTop REST API endpoints for Garena games.
    Returns the itopencodeparam string or None.
    """
    if requests is None:
        return None

    s = session or requests.Session()

    endpoints = [
        "https://itop.kg.garena.vn/auth/login_garena",
        "https://itop.kg.garena.vn/v2/auth/login_garena",
        "https://itop.kg.garena.vn/auth/login",
    ]

    for endpoint in endpoints:
        try:
            resp = s.post(
                endpoint,
                data={
                    "gameid": "1137",
                    "channelid": "10",
                    "openid": open_id,
                    "token": access_token,
                    "uid": str(uid),
                    "os": "1",
                    "lang": "vi",
                    "area": "VN",
                },
                headers={
                    "User-Agent": SDK_USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ret") == 0:
                    itop_openid = data.get("openid", "")
                    itop_token = data.get("token", "")
                    if itop_openid and itop_token:
                        combined = itop_openid + itop_token
                        return combined.upper()
                    encodeparam = data.get("itopencodeparam", "")
                    if encodeparam:
                        return encodeparam
        except Exception:
            continue

    return None


def get_msdk_auth_token(account, password):
    """Full automated flow: login → get itopencodeparam.

    Returns dict with:
        itopencodeparam, open_id, access_token, uid, session_key
    """
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

    account = sys.argv[1]
    password = sys.argv[2]

    print("[*] Logging in as {}...".format(account))
    try:
        result = garena_login(account, password)
        print("[+] Login OK!")
        print("  uid:          {}".format(result["uid"]))
        print("  open_id:      {}".format(result["open_id"]))
        print("  access_token: {}...".format(result["access_token"][:30]))
        print("  session_key:  {}...".format(result["session_key"][:30]))
        print("  expires_in:   {}s".format(result["expires_in"]))

        auth = get_msdk_auth_token(account, password)
        print("\n[+] MSDK auth token:")
        print("  itopencodeparam: {}...".format(auth["itopencodeparam"][:60]))
    except Exception as e:
        print("[-] Failed: {}".format(e))
        sys.exit(1)
