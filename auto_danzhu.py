#!/usr/bin/env python3
"""
Auto Login & Nhap Ma Moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)

Flow:
  1. Garena Connect OAuth: prelogin -> login -> token/grant -> token/exchange
  2. ITOP Game Login: get aov_token, GameOpenId, gameToken
  3. AOV Cloud: danzhu/usecode - nhap ma moi ban be

Usage:
  pip install curl_cffi
  python3 auto_danzhu.py --accounts accounts.txt --code MA_MOI_CUA_BAN

  # Neu van bi captcha, lay datadome cookie tu trinh duyet:
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
import uuid
import re

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    import requests as fallback_requests

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
DEVICE_ID = "57-28-68-BF-29-40-4E-F0-32-40-8B-66-3A-12-E1-F7"

MAX_RETRIES = 3
RETRY_DELAY = 5


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def garena_password_hash(password: str, v2: str) -> str:
    return md5(md5(password) + v2)


def ts_ms() -> str:
    return str(int(time.time() * 1000))


def create_session(datadome_cookie: str = ""):
    if HAS_CURL_CFFI:
        session = curl_requests.Session(impersonate="chrome120")
    else:
        session = fallback_requests.Session()

    if datadome_cookie:
        session.cookies.set("datadome", datadome_cookie, domain=".garena.com")

    return session


def handle_datadome_403(session, resp):
    """
    Xu ly DataDome 403: lay interstitial URL, gui device check, lay cookie moi.
    Tra ve True neu bypass thanh cong.
    """
    try:
        data = resp.json()
    except Exception:
        return False

    interstitial_url = data.get("url", "")
    if not interstitial_url:
        return False

    parsed = urllib.parse.urlparse(interstitial_url)
    params = urllib.parse.parse_qs(parsed.query)

    cid = params.get("cid", [""])[0]
    hash_val = params.get("hash", [""])[0]
    s_val = params.get("s", [""])[0]
    e_val = params.get("e", [""])[0]
    b_val = params.get("b", [""])[0]
    referer = params.get("referer", [""])[0]
    t_val = params.get("t", [""])[0]

    if not cid or not hash_val:
        return False

    # Step 1: GET interstitial page (de lay cookies)
    try:
        interstitial_resp = session.get(interstitial_url, headers={
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        })
    except Exception:
        return False

    # Step 2: POST interstitial device check
    try:
        seed = str(uuid.uuid4())
        post_data = {
            "cid": cid,
            "hash": hash_val,
            "referer": referer or "HTTPS://100054.connect.garena.com/api/prelogin",
            "url": referer or "HTTPS://100054.connect.garena.com/api/prelogin",
            "s": s_val,
            "e": e_val,
            "b": b_val,
            "dm": "jd",
            "seed": seed,
            "ps": "13338",
        }

        check_resp = session.post(
            "https://geo.captcha-delivery.com/interstitial/",
            data=post_data,
            headers={
                "User-Agent": BROWSER_UA,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "*/*",
                "Origin": "https://geo.captcha-delivery.com",
                "Referer": interstitial_url,
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Android WebView";v="150"',
                "sec-ch-ua-mobile": "?1",
                "sec-ch-ua-platform": '"Android"',
                "X-Requested-With": "com.garena.game.kgvn",
            },
        )

        result = check_resp.json()
        cookie_str = result.get("cookie", "")
        if cookie_str and "datadome=" in cookie_str:
            cookie_val = cookie_str.split("datadome=")[1].split(";")[0]
            session.cookies.set("datadome", cookie_val, domain=".garena.com")
            return True
    except Exception:
        pass

    return False


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
        "Referer": (
            f"{GARENA_CONNECT_BASE}/universal/oauth?"
            f"redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
            f"&response_type=code&client_id={GARENA_APP_ID}"
            f"&login_scenario=normal&locale=vi-VN"
        ),
    }

    # Step 0: Load OAuth page for initial cookies
    oauth_url = (
        f"{GARENA_CONNECT_BASE}/api/universal/oauth?"
        f"redirect_uri={urllib.parse.quote(GARENA_REDIRECT_URI)}"
        f"&response_type=code&client_id={GARENA_APP_ID}"
        f"&login_scenario=normal&locale=vi-VN&format=json&id={ts_ms()}"
    )
    session.get(oauth_url, headers=common_headers)
    time.sleep(0.5)

    # Step 1: Prelogin - lay v1, v2 (voi retry DataDome)
    v2 = ""
    for attempt in range(MAX_RETRIES):
        prelogin_url = (
            f"{GARENA_CONNECT_BASE}/api/prelogin?"
            f"app_id={GARENA_APP_ID}"
            f"&account={urllib.parse.quote(account)}"
            f"&format=json&id={ts_ms()}"
        )
        resp = session.get(prelogin_url, headers=common_headers)

        if resp.status_code == 403:
            print(f"  [!] DataDome 403 (lan {attempt+1}/{MAX_RETRIES}), dang thu bypass...")
            bypassed = handle_datadome_403(session, resp)
            if bypassed:
                print(f"  [+] DataDome bypass OK, thu lai...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                if attempt < MAX_RETRIES - 1:
                    print(f"  [!] Bypass khong thanh cong, doi {RETRY_DELAY}s roi thu lai...")
                    time.sleep(RETRY_DELAY)
                    continue
                raise RuntimeError(
                    f"[{account}] DataDome captcha sau {MAX_RETRIES} lan thu.\n"
                    f"  -> Dung --datadome COOKIE de truyen cookie thu cong.\n"
                    f"  -> Lay cookie: Mo trinh duyet -> garena.com -> F12 -> Application -> Cookies -> datadome"
                )

        resp.raise_for_status()
        prelogin_data = resp.json()
        v2 = prelogin_data.get("v2", "")
        if v2:
            break
        if "url" in prelogin_data:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(f"[{account}] Prelogin tra ve captcha URL")

    if not v2:
        raise RuntimeError(f"[{account}] Prelogin khong tra ve v2 sau {MAX_RETRIES} lan thu")

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
    resp = session.get(login_url, headers=common_headers)
    if resp.status_code == 403:
        bypassed = handle_datadome_403(session, resp)
        if bypassed:
            time.sleep(1)
            resp = session.get(login_url, headers=common_headers)
        if resp.status_code == 403:
            raise RuntimeError(f"[{account}] Login bi DataDome captcha.")
    resp.raise_for_status()
    login_data = resp.json()
    if "error" in login_data:
        raise RuntimeError(f"[{account}] Login loi: {login_data}")
    session_key = login_data.get("session_key", "")
    uid = login_data.get("uid", "")
    if not session_key:
        raise RuntimeError(f"[{account}] Login khong co session_key: {login_data}")
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
    resp = session.post(grant_url, data=grant_data, headers=grant_headers)
    resp.raise_for_status()
    grant_result = resp.json()
    code = grant_result.get("code", "")
    if not code:
        raise RuntimeError(f"[{account}] Token grant khong co code: {grant_result}")

    # Step 4: Token Exchange - lay access_token (dung session rieng voi SDK UA)
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
    else:
        exchange_session = fallback_requests.Session()
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
        raise RuntimeError(f"[{account}] Token exchange khong co access_token: {exchange_result}")
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
    else:
        resp = fallback_requests.post(url, data=body, headers=headers, timeout=15)
    resp.raise_for_status()

    try:
        result = resp.json()
    except Exception:
        raise RuntimeError(
            f"ITOP response khong phai JSON (co the can encrypt=1): {resp.text[:200]}"
        )

    if result.get("ret", -1) != 0:
        raise RuntimeError(f"ITOP login loi: ret={result.get('ret')}, msg={result.get('msg','')}")

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
    else:
        resp = fallback_requests.post(url, data=body, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def process_account(account, password, invitation_code, datadome_cookie="", delay=2.0):
    print(f"\n{'='*60}")
    print(f"[*] Dang xu ly: {account}")
    print(f"{'='*60}")

    session = create_session(datadome_cookie)

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
        description="Auto nhap ma moi - Su kien Chung Suc Ban Bi (Lien Quan Mobile VN)"
    )
    parser.add_argument("--accounts", "-a", required=True,
        help="File danh sach tai khoan (account:password)")
    parser.add_argument("--code", "-c", required=True,
        help="Ma moi ban be can nhap (vd: 7Fr64s5RL6)")
    parser.add_argument("--delay", "-d", type=float, default=3.0,
        help="Delay giua cac buoc (giay, mac dinh: 3)")
    parser.add_argument("--account-delay", type=float, default=5.0,
        help="Delay giua cac tai khoan (giay, mac dinh: 5)")
    parser.add_argument("--datadome", default="",
        help="DataDome cookie (lay tu trinh duyet neu bi captcha)")
    args = parser.parse_args()

    if not HAS_CURL_CFFI:
        print("[!] CANH BAO: Khong tim thay curl_cffi - de bi DataDome chan!")
        print("[!] Cai dat: pip install curl_cffi")
        print()

    accounts = load_accounts(args.accounts)
    if not accounts:
        print("[!] Khong tim thay tai khoan nao trong file.")
        sys.exit(1)

    print(f"[*] HTTP client: {'curl_cffi (Chrome TLS)' if HAS_CURL_CFFI else 'requests (de bi chan)'}")
    print(f"[*] Da doc {len(accounts)} tai khoan")
    print(f"[*] Ma moi: {args.code}")
    if args.datadome:
        print(f"[*] DataDome cookie: {args.datadome[:30]}...")

    success = 0
    fail = 0

    for i, (account, password) in enumerate(accounts):
        if i > 0:
            print(f"\n[*] Cho {args.account_delay}s...")
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
