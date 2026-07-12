#!/usr/bin/env python3
"""
KGVN Auto Load Tran v4.0
Tu dong hoa 100%: Chi can nhap tai khoan + mat khau.

Flow:
  1. Dang nhap Garena Connect (tu dong)
  2. Lay token MSDK (tu dong)
  3. Init sign bridge (tu dong)
  4. Chay load tran / boost (tu dong)

Usage:
  python auto_loadtran.py
  python auto_loadtran.py --account user1 --password pass1
  python auto_loadtran.py --accounts accounts.json
  python auto_loadtran.py --accounts accounts.json --dir /sdcard/anh --rounds 3
"""

import argparse
import getpass
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

__version__ = "4.0.0"

try:
    import requests
except ImportError:
    print("\033[91m[!] Thieu: pip install requests\033[0m")
    sys.exit(1)

try:
    from garena_login import (
        garena_login, build_itopencodeparam, build_itopencodeparam_raw,
        try_itop_login,
        get_datadome, parse_har_datadome, save_har_cache, load_har_cache,
    )
except ImportError:
    print("\033[91m[!] Thieu garena_login.py cung thu muc\033[0m")
    sys.exit(1)

from loadtran import (
    C, ok, err, warn, info, dim, bold, hdr, sep, tprint,
    make_session, check_connectivity, gen_traceparent,
    start_sign_bridge, stop_sign_bridge, init_sign_bridge_for_acc,
    get_fresh_encodeparam,
    api_post, cos_put, build_cos_auth,
    build_pic_info, prepare_media, scan_media, resize_to_poster,
    poster_worker, boost_worker,
    countdown, format_duration, cinput, ask_choice,
    FIXED_HEADERS, DEFAULT_USER_AGENT, DEFAULT_SEC_CH_UA,
    COS_BUCKET, COS_REGION, COS_HOST, CDN_BASE, CDN_UGC_BASE,
    API_BASE as _API_BASE,
    IMAGE_EXTS, MAX_MEDIA_PER_ACC,
    POSTER_STAGGER, ROUND_DELAY, ACC_STAGGER,
    PI_BG_ID, PI_BG_PICURL, PI_BG_W, PI_BG_H,
    POSTER_WIDTH, POSTER_HEIGHT,
    COS_UPLOAD_DELAY, CREDS_FETCH_DELAY, SAVE_POSTER_DELAY,
    API_TIMEOUT, COS_UPLOAD_TIMEOUT,
)
import loadtran


_shared_dd = {"dd_cookie": "", "template_cookies": {}, "jspl_payload": ""}


def init_datadome(har_path=None):
    """Initialize DataDome state from HAR or cache. Call once before logins."""
    if har_path:
        har_data = parse_har_datadome(har_path)
        _shared_dd["jspl_payload"] = har_data["jspl_payload"]
        _shared_dd["template_cookies"] = har_data["template_cookies"]
        save_har_cache(har_data["jspl_payload"], har_data["template_cookies"])
        tprint(ok("  HAR parsed: jspl={} bytes, {} cookies".format(
            len(har_data["jspl_payload"]),
            len(har_data["template_cookies"]))))
    else:
        cached = load_har_cache()
        _shared_dd["jspl_payload"] = cached.get("jspl_payload", "")
        _shared_dd["template_cookies"] = cached.get("template_cookies", {})
        if _shared_dd["jspl_payload"]:
            tprint(info("  Dung DataDome cache"))
        else:
            tprint(warn("  Khong co DataDome cache! Chay voi --har <file.har> lan dau"))

    dd, tc = get_datadome(
        _shared_dd["template_cookies"], _shared_dd["jspl_payload"])
    _shared_dd["dd_cookie"] = dd
    if dd:
        tprint(ok("  DataDome cookie OK: {}...".format(dd[:30])))
    else:
        tprint(warn("  Khong lay duoc DataDome cookie"))


def auto_login_account(account, password):
    """Dang nhap Garena va lay token MSDK.

    Returns dict:
        auth_token (itopencodeparam), open_id, access_token, uid, session_key
    """
    tprint(info("  Dang nhap Garena: {}...".format(account)))

    try:
        login_result = garena_login(
            account, password,
            dd_cookie=_shared_dd["dd_cookie"],
            template_cookies=_shared_dd["template_cookies"],
            jspl_payload=_shared_dd["jspl_payload"],
        )
    except Exception as e:
        raise Exception("Garena login that bai: {}".format(str(e)[:100]))

    open_id = login_result["open_id"]
    access_token = login_result["access_token"]
    uid = login_result["uid"]

    if login_result.get("datadome"):
        _shared_dd["dd_cookie"] = login_result["datadome"]

    tprint(ok("  Garena OK! uid={} open_id={}...".format(uid, open_id[:16])))

    # Thu lay token tu iTop
    tprint(info("  Lay MSDK token..."))
    itop_token = try_itop_login(open_id, access_token, uid)
    if itop_token:
        tprint(ok("  iTop auth OK! token={}...".format(itop_token[:30])))
    else:
        itop_token = build_itopencodeparam(open_id, access_token)
        tprint(info("  RSA token: {}...".format(itop_token[:30])))

    return {
        "auth_token": itop_token,
        "open_id": open_id,
        "access_token": access_token,
        "uid": uid,
        "session_key": login_result["session_key"],
        "account": account,
    }


def get_user_path(session, auth_token, encode_param, har_ua, har_sec_ch_ua):
    """Lay user_path tu API bang cach tao poster roi doc COS path."""
    # Tao 1 poster de lay path
    r = api_post(session, "/api/game/poster/playerimage/createposter",
                 {}, auth_token, encode_param, har_ua, har_sec_ch_ua)
    if r.get("code") != 0:
        return None, None

    poster_id = r["data"]["posterId"]

    # Lay COS credentials de biet user_path
    rc = api_post(session, "/api/game/poster/getcoscredential",
                  {"scene": "PlayerimagePoster",
                   "fileName": "0/1/{}.png".format(poster_id)},
                  auth_token, encode_param, har_ua, har_sec_ch_ua)

    if rc.get("code") != 0:
        return poster_id, None

    path = rc.get("data", {}).get("path", "")
    if path:
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            user_path = "/" + "/".join(parts[:3]) + "/"
            return poster_id, user_path

    return poster_id, None


def auto_acc_worker(acc, media_list, rounds, is_share, acc_results):
    """Worker thread xu ly 1 account (auto-login mode)."""
    account = acc["account"]
    password = acc["password"]
    lbl = acc.get("label", account)

    tprint("\n" + sep(62, "=", C.CYAN))
    tprint("{}{}  START  {}{}".format(C.CYAN + C.BOLD, ">", lbl, C.RESET))
    tprint(sep(62, "=", C.CYAN))

    # Step 1: Auto login
    try:
        login_data = auto_login_account(account, password)
    except Exception as e:
        tprint(err("  [{}] Login FAIL: {}".format(lbl, str(e)[:60])))
        acc_results[lbl] = {"ok": 0, "fail": 0, "rounds": []}
        return

    auth_token = login_data["auth_token"]
    encode_param = None
    har_ua = DEFAULT_USER_AGENT
    har_sec_ch_ua = DEFAULT_SEC_CH_UA

    # Step 2: Init sign bridge
    sess = make_session()
    bridge_ok = init_sign_bridge_for_acc(
        sess, auth_token, encode_param, har_ua, har_sec_ch_ua)
    if not bridge_ok:
        tprint(warn("  [{}] Sign bridge init FAIL — chay khong co sign".format(lbl)))

    tprint(dim("  Token   : {}...".format(auth_token[:35])))

    sess = make_session()

    # Step 3: Lay user_path
    tprint(info("  Lay user_path..."))
    first_pid, user_path = get_user_path(
        sess, auth_token, encode_param, har_ua, har_sec_ch_ua)

    if not user_path:
        tprint(err("  [{}] Khong lay duoc user_path — bo qua".format(lbl)))
        acc_results[lbl] = {"ok": 0, "fail": 0, "rounds": []}
        return

    tprint(ok("  user_path = {}".format(user_path)))
    tprint(dim("  COS     : {}".format(user_path)))

    # Step 4: Lay picInfo
    tprint(info("  Lay picInfo hien tai..."))
    r = api_post(sess, "/api/game/poster/playerimage/getpostereditinfo",
                 {}, auth_token, encode_param, har_ua, har_sec_ch_ua)
    if r.get("code") == 0 and r.get("data", {}).get("picInfo"):
        pic_info_raw = r["data"]["picInfo"]
        tprint(ok("  picInfo OK"))
    else:
        pic_info_raw = {}
        tprint(warn("  Dung cau hinh mac dinh"))
    time.sleep(COS_UPLOAD_DELAY)

    # Step 5: Chay poster workflow (giong acc_worker goc)
    n_media = len(media_list)
    total_ok = total_fail = 0
    round_logs = []

    for rnd in range(1, rounds + 1):
        tprint("")
        tprint("{}  [{}] Vong {:02d}/{:02d}  —  {} media song song{}".format(
            C.CYAN + C.BOLD, lbl[:16], rnd, rounds, n_media, C.RESET))

        results = [None] * n_media
        threads = []
        for i, m in enumerate(media_list, 1):
            t = threading.Thread(
                target=poster_worker,
                args=(i, lbl, auth_token, encode_param, user_path,
                      m, pic_info_raw, is_share,
                      har_ua, har_sec_ch_ua, results),
                daemon=True,
            )
            threads.append(t)

        for t in threads:
            t.start()
            time.sleep(POSTER_STAGGER)

        for t in threads:
            t.join()

        ok_n = sum(1 for res in results if res and res[0])
        fail_n = n_media - ok_n
        total_ok += ok_n
        total_fail += fail_n
        round_logs.append((rnd, results))

        summary = "{} OK  {} FAIL".format(
            "{}{}{}".format(C.GREEN, ok_n, C.RESET),
            "{}{}{}".format(C.RED, fail_n, C.RESET))
        tprint("  {}[{}] Vong {:02d}: {}{}".format(
            C.BOLD, lbl[:16], rnd, summary, C.RESET))

        if rnd < rounds:
            tprint(dim("  [{}] Nghi {}s truoc vong tiep...".format(
                lbl[:16], ROUND_DELAY)))
            time.sleep(ROUND_DELAY)

    # Tong ket acc
    tprint("")
    tprint("{}|- DONE: {} {}".format(C.CYAN + C.BOLD, lbl, C.RESET))
    for rnd, results in round_logs:
        for i, res in enumerate(results, 1):
            g = (rnd - 1) * n_media + i
            if res and res[0]:
                kind = res[3] if len(res) > 3 else "?"
                tprint("{}|{}  V{:02d}#{:02d} {}  [{}]  ID={}".format(
                    C.CYAN, C.RESET, rnd, g, ok("OK"), kind, res[1]))
            else:
                msg = str(res[1])[:35] if res else "?"
                tprint("{}|{}  V{:02d}#{:02d} {}  {}".format(
                    C.CYAN, C.RESET, rnd, g, err("FAIL"), msg))
    tprint("{}|- OK:{} {}{}{}  FAIL:{} {}{}{}  TONG:{}{}".format(
        C.CYAN,
        C.RESET, C.GREEN + C.BOLD, total_ok, C.RESET,
        C.RESET, C.RED + C.BOLD, total_fail, C.RESET,
        C.BOLD, rounds * n_media) + C.RESET)

    acc_results[lbl] = {"ok": total_ok, "fail": total_fail, "rounds": round_logs}


def load_accounts_file(filepath):
    """Doc file accounts JSON.

    Format:
    [
      {"account": "user1", "password": "pass1"},
      {"account": "user2", "password": "pass2"}
    ]
    hoac:
    [
      {"account": "user1", "password": "pass1", "label": "TK chinh"}
    ]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    for acc in data:
        if "account" not in acc or "password" not in acc:
            raise ValueError("Moi acc can co 'account' va 'password'")
        if "label" not in acc:
            acc["label"] = acc["account"]
    return data


def input_accounts_interactive():
    """Nhap tai khoan tuong tac."""
    accounts = []

    idx = 1
    while True:
        if idx == 1:
            print("")
        print("  {}--- Tai khoan #{} ---{}".format(C.CYAN, idx, C.RESET))
        acc = cinput("  Tai khoan Garena: ")
        if not acc:
            if accounts:
                break
            print(warn("Nhap tai khoan!"))
            continue

        pw = getpass.getpass("  Mat khau: ")
        if not pw:
            print(warn("Mat khau khong duoc de trong!"))
            continue

        accounts.append({
            "account": acc,
            "password": pw,
            "label": acc,
        })
        print(ok("  OK: {}".format(acc)))
        idx += 1

        more = cinput("\n  Them tai khoan nua? (y/N): ")
        if more.lower() not in ("y", "yes", "co", "c"):
            break

    return accounts


def run_auto(accounts, image_dir, rounds_arg, dry_run=False, har_path=None):
    """Ham chinh — che do tu dong."""
    start_time = time.time()

    print("")
    print("{}{}".format(C.CYAN, "=" * 62))
    print("{}  KGVN  Auto Load Tran  v4.0  —  100% Tu Dong     ".format(
        C.WHITE + C.BOLD))
    print("{}  Dang nhap tu dong | Sign Bridge | COS Upload  ".format(C.CYAN))
    print("{}{}".format(C.CYAN, "=" * 62) + C.RESET)

    if dry_run:
        print("\n" + warn("CHE DO DRY-RUN: Chi kiem tra, KHONG upload"))

    # Kiem tra ket noi
    print("\n" + info("Kiem tra ket noi..."))
    if not check_connectivity():
        print(err("Khong co ket noi internet!"))
        sys.exit(1)
    print(ok("Mang OK"))

    # Set API base
    loadtran.API_BASE = "https://kgvn-api.mobagarena.com"

    # Khoi dong sign bridge (can truoc login de tao itopencodeparam)
    bridge_ok = start_sign_bridge()
    if not bridge_ok:
        print(warn("Sign bridge KHONG HOAT DONG."))
        print(info("Se chay khong co sign."))

    # Init DataDome
    print("\n" + info("Khoi tao DataDome bypass..."))
    init_datadome(har_path)

    # Hien thi danh sach accounts
    n_acc = len(accounts)
    print("\n" + bold("{} tai khoan:".format(n_acc)))
    for i, acc in enumerate(accounts, 1):
        print("  {}{:02d}.{} {}".format(
            C.YELLOW, i, C.RESET, acc["label"]))

    # Xac thuc tat ca accounts truoc
    print("\n" + bold("Dang nhap tat ca tai khoan..."))
    valid_accounts = []
    for acc in accounts:
        try:
            login_data = auto_login_account(acc["account"], acc["password"])
            acc["_login"] = login_data
            valid_accounts.append(acc)
            tprint(ok("  {} — OK".format(acc["label"])))
        except Exception as e:
            tprint(err("  {} — FAIL: {}".format(acc["label"], str(e)[:60])))

    if not valid_accounts:
        print(err("Khong co tai khoan nao dang nhap thanh cong!"))
        sys.exit(1)

    print("\n  {} / {} tai khoan hop le".format(
        "{}{}{}".format(C.GREEN, len(valid_accounts), C.RESET),
        n_acc))

    # Chon chuc nang
    main_mode = ask_choice(
        "Chon chuc nang:",
        {"1": "{}Mod media poster{} (JPG / PNG / GIF / MP4)".format(
            C.GREEN + C.BOLD, C.RESET),
         "2": "{}Tang luot dung nen{} (Boost)".format(
             C.YELLOW + C.BOLD, C.RESET)}
    )

    # =========================================================
    # BOOST MODE
    # =========================================================
    if main_mode == "2":
        print("\n" + bold("Nhap thong tin poster:"))
        poster_id = cinput("  PosterId  : ")
        try:
            count = int(cinput("  So lan    : "))
            d = cinput("  Delay giay [mac dinh 1.0]: ")
            delay_s = float(d) if d else 1.0
        except ValueError:
            print(err("Nhap sai"))
            sys.exit(1)

        boost_results = {}
        threads = []
        for acc in valid_accounts:
            login_d = acc["_login"]
            t = threading.Thread(
                target=boost_worker,
                args=(acc["label"], login_d["auth_token"], None,
                      DEFAULT_USER_AGENT, DEFAULT_SEC_CH_UA,
                      poster_id, count, delay_s, boost_results),
                daemon=True,
            )
            threads.append(t)

        print("\n" + bold("Bat dau boost {} acc SONG SONG...".format(
            len(valid_accounts))))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start_time
        print("\n" + sep(62, "=", C.CYAN))
        print("{}  BOOST TONG KET  ({} acc)  T {}{}".format(
            C.WHITE + C.BOLD, len(valid_accounts),
            format_duration(elapsed), C.RESET))
        print(sep(62, "-", C.GRAY))
        grand_ok = grand_fail = 0
        for lbl, res in boost_results.items():
            print("  {:<32}  {}OK:{:<5}{}  {}FAIL:{}{}".format(
                lbl[:32],
                C.GREEN, res["ok"], C.RESET,
                C.RED, res["fail"], C.RESET))
            grand_ok += res["ok"]
            grand_fail += res["fail"]
        print(sep(62, "-", C.GRAY))
        print("  {}TONG: OK={}  FAIL={}{}".format(
            C.BOLD, grand_ok, grand_fail, C.RESET))
        print(sep(62, "=", C.CYAN))
        return

    # =========================================================
    # MOD POSTER MODE
    # =========================================================

    # Scan media
    print("\n" + info("Quet media trong: " + image_dir))
    all_files = scan_media(image_dir)
    print("  Tim thay {} file:".format(len(all_files)))
    TYPE_COLORS = {
        ".jpg":  "{}JPG{}".format(C.YELLOW, C.RESET),
        ".jpeg": "{}JPG{}".format(C.YELLOW, C.RESET),
        ".png":  "{}PNG{}".format(C.CYAN, C.RESET),
        ".webp": "{}WEBP{}".format(C.CYAN, C.RESET),
        ".gif":  "{}GIF{}".format(C.GREEN + C.BOLD, C.RESET),
        ".mp4":  "{}MP4{}".format(C.PURPLE + C.BOLD, C.RESET),
    }
    for i, p in enumerate(all_files, 1):
        tc = TYPE_COLORS.get(p.suffix.lower(), p.suffix.upper())
        print("  {}[{}]{}  {}  {}  {:.1f} KB".format(
            C.YELLOW, i, C.RESET, tc, p.name, p.stat().st_size / 1024))

    n_valid = len(valid_accounts)

    # Phan cong anh
    if len(all_files) == 1:
        img_mode = "2"
        print("\n" + info("1 file duy nhat — tat ca acc dung chung."))
    else:
        if len(all_files) < n_valid:
            print("\n" + warn("{} file < {} acc — mode 1 se lap vong anh.".format(
                len(all_files), n_valid)))
        img_mode = ask_choice(
            "Che do phan cong media:",
            {"1": "Moi acc {}1 bo rieng{}  (acc1->file1, acc2->file2, ...)".format(
                C.BOLD, C.RESET),
             "2": "Tat ca acc dung {}chung{}  (toi da {} file/acc)".format(
                 C.BOLD, C.RESET, MAX_MEDIA_PER_ACC)}
        )

    if img_mode == "1":
        print("\n  Phan cong (rieng):")
        for i, a in enumerate(valid_accounts):
            f = all_files[i % len(all_files)]
            print("    {}{}{}  ->  {}".format(
                C.CYAN, a["label"][:30], C.RESET, f.name))
    else:
        shared = all_files[:MAX_MEDIA_PER_ACC]
        print("\n" + info("Dung chung {} file: {}".format(
            len(shared), ", ".join(p.name for p in shared))))

    # Che do luu
    save_mode = ask_choice(
        "Che do LUU:",
        {"1": "{}Luu rieng{}  (chi minh toi dung)".format(C.CYAN, C.RESET),
         "2": "{}Quang truong{}  (moi nguoi thay)".format(C.YELLOW, C.RESET)}
    )
    is_share = (save_mode == "2")

    # So vong
    if rounds_arg:
        rounds = max(1, rounds_arg)
    else:
        raw = cinput("\n  So vong lap (ENTER=1): ")
        try:
            rounds = int(raw) if raw else 1
            rounds = max(1, rounds)
        except ValueError:
            rounds = 1

    # Pre-process media
    print("\n" + info("Xu ly media truoc khi chay..."))
    shared_media = None
    if img_mode == "2":
        shared_files = all_files[:MAX_MEDIA_PER_ACC]
        shared_media = []
        for p in shared_files:
            print(info("  Xu ly: {}".format(p.name)))
            shared_media.append(prepare_media(p))

    acc_media_map = {}
    for i, a in enumerate(valid_accounts):
        lbl = a["label"]
        if img_mode == "1":
            f = all_files[i % len(all_files)]
            print(info("  {} -> {}".format(lbl[:25], f.name)))
            acc_media_map[lbl] = [prepare_media(f)]
        else:
            acc_media_map[lbl] = shared_media

    imgs_per = len(shared_media) if img_mode == "2" else 1
    grand_total = rounds * imgs_per * n_valid
    print("\n  {} acc  x  {} vong  =  {}{}{}  poster tong".format(
        n_valid, rounds, C.CYAN + C.BOLD, grand_total, C.RESET))

    if dry_run:
        elapsed = time.time() - start_time
        print("\n" + sep(62, "=", C.CYAN))
        print("{}  DRY-RUN HOAN TAT  ({}){}".format(
            C.WHITE + C.BOLD, format_duration(elapsed), C.RESET))
        print(ok("Tat ca {} acc hop le, {} media san sang.".format(
            n_valid, len(all_files))))
        print(info("Bo --dry-run de chay that.\n"))
        return

    # Confirm
    confirm = cinput("\n  Nhap 'ok' de bat dau, Ctrl+C de huy: ")
    if confirm.lower() != "ok":
        print(err("Huy"))
        sys.exit(0)

    # Spawn threads
    acc_results = {}
    threads = []
    print("\n" + bold("Bat dau {} acc SONG SONG...".format(n_valid)))
    for a in valid_accounts:
        t = threading.Thread(
            target=auto_acc_worker,
            args=(a, acc_media_map[a["label"]], rounds, is_share, acc_results),
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(ACC_STAGGER)

    for t in threads:
        t.join()

    # Tong ket
    elapsed = time.time() - start_time
    print("")
    print(sep(62, "=", C.CYAN))
    print("{}  TONG KET  ({} acc)  T {}{}".format(
        C.WHITE + C.BOLD, n_valid, format_duration(elapsed), C.RESET))
    print(sep(62, "-", C.GRAY))
    grand_ok = grand_fail = 0
    for a in valid_accounts:
        res = acc_results.get(a["label"], {"ok": 0, "fail": 0})
        ok_a, fail_a = res["ok"], res["fail"]
        grand_ok += ok_a
        grand_fail += fail_a
        print("  {}{:<30}{}  {}OK:{:<4}{}  {}FAIL:{:<4}{}  TONG:{}".format(
            C.CYAN, a["label"][:30], C.RESET,
            C.GREEN, ok_a, C.RESET,
            C.RED, fail_a, C.RESET,
            ok_a + fail_a))
    print(sep(62, "-", C.GRAY))
    print("  {}TONG CONG:  OK={}{}{}  FAIL={}{}{}  /  {} poster{}".format(
        C.BOLD,
        C.GREEN, grand_ok, C.RESET + C.BOLD,
        C.RED, grand_fail, C.RESET + C.BOLD,
        grand_total, C.RESET))
    print(sep(62, "=", C.CYAN))
    print("\n  {}Mo game -> Anh load tran de thay!{}\n".format(C.CYAN, C.RESET))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="KGVN Auto Load Tran v4.0 — Tu dong 100%%",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "SU DUNG:\n"
            "  # Nhap tuong tac:\n"
            "  python auto_loadtran.py\n\n"
            "  # 1 tai khoan:\n"
            "  python auto_loadtran.py --account user1 --password pass1\n\n"
            "  # Nhieu tai khoan tu file:\n"
            "  python auto_loadtran.py --accounts accounts.json\n\n"
            "  # Lan dau (can HAR de bypass DataDome):\n"
            "  python auto_loadtran.py --har game.har\n\n"
            "  # Voi tuy chon:\n"
            "  python auto_loadtran.py --accounts accounts.json "
            "--dir ./anh --rounds 3\n\n"
            "FILE accounts.json FORMAT:\n"
            '  [{"account":"user1","password":"pass1","label":"TK 1"},\n'
            '   {"account":"user2","password":"pass2"}]\n\n'
            "CAI DAT:\n"
            "  pip install requests Pillow pycryptodome\n"
        ),
    )
    ap.add_argument("--version", action="version",
                    version="%(prog)s " + __version__)
    ap.add_argument("--account", "-u",
                    help="Ten dang nhap Garena")
    ap.add_argument("--password", "-p",
                    help="Mat khau Garena")
    ap.add_argument("--accounts", "-a",
                    help="File JSON chua danh sach tai khoan")
    ap.add_argument("--dir", default=".",
                    help="Thu muc chua media (mac dinh: .)")
    ap.add_argument("--rounds", type=int, default=None,
                    help="So vong lap")
    ap.add_argument("--har",
                    help="File HAR (HTTP Archive) de lay DataDome bypass.\n"
                         "Chi can lan dau, sau do dung cache.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chi kiem tra, khong upload")
    args = ap.parse_args()

    accounts = []

    if args.accounts:
        try:
            accounts = load_accounts_file(args.accounts)
            print(ok("Doc {} tai khoan tu {}".format(
                len(accounts), args.accounts)))
        except Exception as e:
            print(err("Loi doc file accounts: {}".format(e)))
            sys.exit(1)
    elif args.account:
        pw = args.password
        if not pw:
            pw = getpass.getpass("Mat khau cho {}: ".format(args.account))
        accounts = [{"account": args.account, "password": pw,
                      "label": args.account}]
    else:
        accounts = input_accounts_interactive()

    if not accounts:
        print(err("Khong co tai khoan nao!"))
        sys.exit(1)

    if args.har and not os.path.exists(args.har):
        print(err("File HAR khong ton tai: {}".format(args.har)))
        sys.exit(1)

    try:
        run_auto(accounts, args.dir, args.rounds, args.dry_run, args.har)
    except KeyboardInterrupt:
        print("\n" + err("Huy boi nguoi dung"))
    finally:
        stop_sign_bridge()
