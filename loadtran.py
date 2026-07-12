#!/usr/bin/env python3
import argparse
import hashlib
import hmac as hmac_lib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from datetime import datetime

__version__ = "4.0.0"

_LICENSE_URL = ""
_USES_FILE = "/dev/null"
_0xSESSION = None

def _0xD1():
    return "bypassed_device"

def _0xD2():
    try:
        with open(_USES_FILE) as f: return int(f.read().strip())
    except: return 0

def _0xD3(n):
    try:
        with open(_USES_FILE, 'w') as f: f.write(str(n))
    except: pass

def _0xXR(data, key):
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))

def _0xD4():
    try:
        return {"api": "https://kgvn-api.mobagarena.com"}
    except:
        return None

def _0xCK():
    return # Bypassed
    if time.time() - _0xSESSION.get('ts', 0) > 7200: sys.exit(1)
    if not _0xSESSION.get('ep', '').startswith('https://'): sys.exit(1)

def _0xEP():
    _0xCK()
    return _0xSESSION['ep']

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("\033[91m[!] Thieu: pip install requests\033[0m")
    sys.exit(1)

try:
    from PIL import Image as _PIL_Image
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

# =============================================================================
# ANSI COLORS
# =============================================================================

class C:
    """ANSI color codes cho terminal output."""
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    PURPLE = "\033[95m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"
    BG_CYAN   = "\033[46m"
    BG_GREEN  = "\033[42m"
    BG_RED    = "\033[41m"
    BG_PURPLE = "\033[45m"

def ok(msg):   return "{}✓  {}{}".format(C.GREEN,  msg, C.RESET)
def err(msg):  return "{}✗  {}{}".format(C.RED,    msg, C.RESET)
def warn(msg): return "{}⚠  {}{}".format(C.YELLOW, msg, C.RESET)
def info(msg): return "{}›  {}{}".format(C.CYAN,   msg, C.RESET)
def dim(msg):  return "{}{}{}".format(C.GRAY, msg, C.RESET)
def bold(msg): return "{}{}{}".format(C.BOLD, msg, C.RESET)

def hdr(title, width=62):
    """Tao header voi vien trang tri."""
    inner = " {} ".format(title)
    pad   = max(0, width - len(inner) - 2)
    l, r  = pad // 2, pad - pad // 2
    return ("{}{}{}  {}{}{}{}  {}{}".format(
        C.BG_CYAN, C.WHITE, C.BOLD,
        "─"*l, inner, "─"*r,
        C.RESET, C.CYAN, C.RESET))

def sep(width=62, char="─", color=C.GRAY):
    """Tao dong phan cach."""
    return "{}{}{}".format(color, char*width, C.RESET)

# =============================================================================
# CAU HINH  (v3.0 — Sign Bridge, Boost, COS creds rieng)
# =============================================================================

COS_BUCKET   = "aovcamp-h5-ugc-1254801811"
COS_REGION   = "ap-singapore"
COS_HOST     = "{}.cos.{}.myqcloud.com".format(COS_BUCKET, COS_REGION)
CDN_BASE     = "https://kg-camp.mobagarena.com"
CDN_UGC_BASE = "https://kg-camp-ugc.mobagarena.com"
API_BASE     = None  # Set by license session
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"}
MAX_MEDIA_PER_ACC = 6
DEFAULT_HAR  = "v9.har"

# Kich thuoc chuan poster load tran
POSTER_WIDTH  = 1080
POSTER_HEIGHT = 1701

# Playerimage constants
PI_BG_ID      = "21"
PI_BG_PICURL  = CDN_BASE + "/manage/playerimage_official/iDzT817p.png"
PI_BG_W       = 320
PI_BG_H       = 503.9935570469799

# Timing constants (seconds)
POSTER_STAGGER    = 3.6
ROUND_DELAY       = 3.0
ACC_STAGGER       = 2.0
COS_UPLOAD_DELAY  = 0.5
CREDS_FETCH_DELAY = 0.3
SAVE_POSTER_DELAY = 1.5
API_TIMEOUT       = 25
COS_UPLOAD_TIMEOUT = 60

# Sign bridge
SIGN_BRIDGE_PORT = 19876
SIGN_BRIDGE_URL  = "http://127.0.0.1:{}".format(SIGN_BRIDGE_PORT)

# Fallback User-Agent / sec-ch-ua — se bi override boi gia tri tu HAR
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 16; CPH2747 Build/BP2A.250605.015; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/149.0.7827.91 "
    "Mobile Safari/537.36 MSDK/5.36.000 mQQAppId/1105779914 "
    "mWXAppId/wx7a814e3ceeda8320 mGameId/1137 MSDKdeviceId/disable"
)
DEFAULT_SEC_CH_UA = '"Android WebView";v="149", "Chromium";v="149", "Not)A;Brand";v="24"'

FIXED_HEADERS = {
    "camp-source":        "AOV-CAMP",
    "msdk-gameid":        "1137",
    "camp-authtype":      "msdk",
    "areaid":             "1",
    "msdk-os":            "1",
    "logicworldid":       "1011",
    "aov-language":       "VN",
    "msdk-channelid":     "10",
    "aov-region":         "1137",
    "origin":             "https://kgvn-camp.mobagarena.com",
    "x-requested-with":   "com.garena.game.kgvn",
    "referer":            "https://kgvn-camp.mobagarena.com/",
    "sec-ch-ua-mobile":   "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-site":     "same-site",
    "sec-fetch-mode":     "cors",
    "sec-fetch-dest":     "empty",
    "accept":             "*/*",
    "accept-language":    "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "accept-encoding":    "gzip, deflate, br, zstd",
}

_print_lock = threading.Lock()
def tprint(msg):
    """Thread-safe print."""
    with _print_lock:
        print(msg, flush=True)

# =============================================================================
# SIGN BRIDGE (Node.js / Python subprocess for encodeparam)
# =============================================================================

_sign_bridge_proc = None
_sign_session     = None
_sign_lock        = threading.Lock()
_camp_roleid      = ""

def _find_node():
    """Tim Node.js binary."""
    for cmd in ["node", "nodejs"]:
        try:
            r = subprocess.run([cmd, "--version"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.SubprocessError):
            continue
    termux = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    node_path = os.path.join(termux, "bin", "node")
    if os.path.isfile(node_path):
        return node_path
    return None

def start_sign_bridge():
    """Khoi dong sign bridge. Thu Python bridge truoc (cho iSH), roi Node.js."""
    global _sign_bridge_proc, _sign_session

    script_dir = os.path.dirname(os.path.abspath(__file__))
    security_js = os.path.join(script_dir, "camp-security-oversea.0.1.0.js")
    if not os.path.isfile(security_js):
        tprint(warn("camp-security-oversea.0.1.0.js khong tim thay!"))
        return False

    # --- Thu Python bridge (nhanh hon tren iSH) ---
    py_bridge = os.path.join(script_dir, "sign_bridge_py.py")
    _is_ish = os.path.isfile("/etc/alpine-release") if sys.platform != "win32" else False
    if _is_ish and os.path.isfile(py_bridge):
        tprint(info("Thu Python sign bridge (iSH mode)..."))
        try:
            python_cmd = sys.executable or "python3"
            _sign_bridge_proc = subprocess.Popen(
                [python_cmd, py_bridge, str(SIGN_BRIDGE_PORT)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=script_dir,
            )
            for _ in range(120):
                time.sleep(0.5)
                if _sign_bridge_proc.poll() is not None:
                    break
                try:
                    _sign_session = requests.Session()
                    r = _sign_session.get(SIGN_BRIDGE_URL + "/health", timeout=2)
                    if r.status_code == 200:
                        tprint(ok("Python sign bridge san sang!"))
                        return True
                except Exception:
                    pass
            tprint(warn("Python bridge khong san sang, thu Node.js..."))
            try:
                _sign_bridge_proc.terminate()
            except Exception:
                pass
            _sign_bridge_proc = None
        except Exception as e:
            tprint(warn("Python bridge loi: " + str(e)[:60]))

    # --- Node.js bridge ---
    node = _find_node()
    if not node:
        tprint(warn("Node.js khong tim thay!"))
        tprint(info("  Cai dat: pkg install nodejs"))
        return False

    tprint(info("Node.js: {}".format(node)))

    bridge_js = os.path.join(script_dir, "sign_bridge.js")
    if not os.path.isfile(bridge_js):
        tprint(warn("sign_bridge.js khong tim thay!"))
        return False

    tprint(info("Khoi dong sign bridge..."))
    try:
        _sign_bridge_proc = subprocess.Popen(
            [node, bridge_js, "--serve", str(SIGN_BRIDGE_PORT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=script_dir,
        )

        _stdout_buf = []
        _stderr_buf = []

        def _read_stream(stream, buf):
            try:
                for line in iter(stream.readline, b""):
                    buf.append(line)
            except Exception:
                pass

        t_out = threading.Thread(target=_read_stream,
                                 args=(_sign_bridge_proc.stdout, _stdout_buf),
                                 daemon=True)
        t_err = threading.Thread(target=_read_stream,
                                 args=(_sign_bridge_proc.stderr, _stderr_buf),
                                 daemon=True)
        t_out.start()
        t_err.start()

        _is_ish2 = False
        try:
            _is_ish2 = os.path.isfile("/etc/alpine-release") or "ish" in os.uname().nodename.lower()
        except Exception:
            pass
        _bridge_timeout = 60 if _is_ish2 else 10
        deadline = time.time() + _bridge_timeout
        ready = False
        while time.time() < deadline:
            if _sign_bridge_proc.poll() is not None:
                t_out.join(timeout=1)
                t_err.join(timeout=1)
                stderr_txt = b"".join(_stderr_buf).decode(errors="ignore")
                tprint(err("Sign bridge thoat som!"))
                for line in stderr_txt.strip().split("\n")[:8]:
                    if line.strip():
                        tprint(dim("  [node] " + line.strip()[:80]))
                _sign_bridge_proc = None
                return False

            for line in _stdout_buf:
                try:
                    data = json.loads(line.decode().strip())
                    if data.get("ready"):
                        ready = True
                        break
                except Exception:
                    pass
            if ready:
                break
            time.sleep(0.3)

        if ready:
            _sign_session = requests.Session()
            try:
                r = _sign_session.get(SIGN_BRIDGE_URL + "/health", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    tprint(ok("Sign bridge san sang (tcsj={}, methods={})".format(
                        data.get("tcsj"),
                        ",".join(data.get("methods", [])))))
                    return True
                else:
                    tprint(warn("Sign bridge health fail: {}".format(r.status_code)))
                    return False
            except Exception as e:
                tprint(warn("Sign bridge health loi: " + str(e)[:60]))
                return False
        else:
            t_out.join(timeout=1)
            t_err.join(timeout=1)
            stderr_txt = b"".join(_stderr_buf).decode(errors="ignore")
            tprint(warn("Sign bridge TIMEOUT ({}s)".format(_bridge_timeout)))
            for line in stderr_txt.strip().split("\n")[:10]:
                if line.strip():
                    tprint(dim("  [node] " + line.strip()[:80]))
            try:
                _sign_bridge_proc.terminate()
            except Exception:
                pass
            _sign_bridge_proc = None
            return False

    except Exception as e:
        tprint(err("Loi khoi dong sign bridge: " + str(e)[:80]))
        return False

def stop_sign_bridge():
    """Tat sign bridge."""
    global _sign_bridge_proc
    if _sign_bridge_proc:
        try:
            _sign_bridge_proc.terminate()
            _sign_bridge_proc.wait(timeout=3)
        except Exception:
            try:
                _sign_bridge_proc.kill()
            except Exception:
                pass
        _sign_bridge_proc = None

def get_fresh_encodeparam(body_str="{}", roleid="", fallback_ep=None):
    """Lay encodeparam moi tu sign bridge."""
    if not _sign_session or not _sign_bridge_proc:
        return fallback_ep
    if _sign_bridge_proc.poll() is not None:
        tprint(warn("Sign bridge process da thoat!"))
        return fallback_ep
    rid = roleid or _camp_roleid
    with _sign_lock:
        try:
            r = _sign_session.post(
                SIGN_BRIDGE_URL + "/sign",
                json={"roleid": rid},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                ep = data.get("encodeparam")
                if ep and len(ep) > 10:
                    return ep
                else:
                    tprint(warn("Sign bridge tra ve ep rong: {}".format(
                        str(data)[:80])))
            else:
                tprint(warn("Sign bridge HTTP {}: {}".format(
                    r.status_code, r.text[:80])))
        except Exception as e:
            tprint(warn("Sign bridge loi: {}".format(str(e)[:60])))
    return fallback_ep

def init_sign_bridge_for_acc(session, auth_token, encode_param,
                             har_ua, har_sec_ch_ua):
    """Goi getselfuserinfo de lay encryption + campRoleid, roi init bridge."""
    if not _sign_session or not _sign_bridge_proc:
        return False

    tprint(info("  Khoi tao sign bridge (getselfuserinfo)..."))

    hdrs = dict(FIXED_HEADERS)
    hdrs["content-type"]         = "application/json"
    hdrs["msdk-itopencodeparam"] = auth_token
    hdrs["traceparent"]          = gen_traceparent()
    hdrs["priority"]             = "u=1, i"
    hdrs["user-agent"]           = har_ua or DEFAULT_USER_AGENT
    hdrs["sec-ch-ua"]            = har_sec_ch_ua or DEFAULT_SEC_CH_UA
    if encode_param:
        hdrs["encodeparam"]      = encode_param

    try:
        r = session.post(
            API_BASE + "/api/user/game/getselfuserinfo",
            headers=hdrs,
            json={},
            timeout=10,
        )
        data = r.json()
        if data.get("code") != 0:
            tprint(warn("  getselfuserinfo code={} msg={}".format(
                data.get("code"), data.get("msg", "")[:60])))
            return False

        userdata = data.get("data", {})
        encryption = userdata.get("encryption")
        role = userdata.get("role", {})
        camp_roleid = role.get("campRoleid", "")

        if not encryption:
            tprint(warn("  getselfuserinfo: khong co encryption"))
            return False

        tprint(info("  campRoleid={}".format(camp_roleid)))

        global _camp_roleid
        _camp_roleid = camp_roleid

        r2 = _sign_session.post(
            SIGN_BRIDGE_URL + "/init",
            json={"encryption": encryption, "campRoleid": camp_roleid},
            timeout=5,
        )
        if r2.status_code == 200:
            init_data = r2.json()
            if init_data.get("ok"):
                test_ep = init_data.get("testEncodeparam", "")
                tprint(ok("  Sign bridge init OK! (ep={})".format(
                    test_ep[:30] + "..." if test_ep else "?")))
                return True
            else:
                tprint(warn("  Sign bridge init response: {}".format(
                    str(init_data)[:80])))
                return False
        else:
            tprint(warn("  Sign bridge init HTTP {}: {}".format(
                r2.status_code, r2.text[:80])))
            return False

    except Exception as e:
        tprint(warn("  init_sign_bridge loi: {}".format(str(e)[:80])))
        return False

# =============================================================================
# UTILS
# =============================================================================

def gen_traceparent():
    """Tao traceparent header ngau nhien (W3C Trace Context)."""
    return "00-{}-{}-01".format(os.urandom(16).hex(), os.urandom(8).hex())

def check_connectivity():
    """Kiem tra ket noi internet."""
    for host, port in [("kgvn-api.mobagarena.com", 443), ("8.8.8.8", 53)]:
        try:
            conn = socket.create_connection((host, port), timeout=5)
            conn.close()
            return True
        except (socket.timeout, socket.error, OSError):
            continue
    return False

def make_session():
    """Tao requests.Session voi retry policy."""
    s = requests.Session()
    r = Retry(total=3, backoff_factor=1.5,
              status_forcelist=[500, 502, 503, 504],
              allowed_methods=["POST", "PUT", "GET"])
    a = HTTPAdapter(max_retries=r)
    s.mount("https://", a)
    s.mount("http://", a)
    return s

def ask_choice(prompt, options):
    """Hien thi menu lua chon va tra ve key duoc chon."""
    print("\n" + "{}{}{}".format(C.CYAN, prompt, C.RESET))
    for k, v in options.items():
        print("    {}[{}]{} {}".format(C.YELLOW+C.BOLD, k, C.RESET, v))
    while True:
        try:
            c = input("    {}Chon: {}".format(C.PURPLE, C.RESET)).strip()
            if c in options:
                return c
            print(warn("Nhap: " + " / ".join(options.keys())))
        except KeyboardInterrupt:
            print("\n" + err("Huy")); sys.exit(0)

def cinput(prompt):
    """Input voi mau sac, xu ly Ctrl+C."""
    try:
        return input("{}{}{}".format(C.PURPLE, prompt, C.RESET)).strip()
    except KeyboardInterrupt:
        print("\n" + err("Huy")); sys.exit(0)

def has_ffmpeg():
    """Kiem tra ffmpeg co san khong."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

def format_duration(seconds):
    """Format so giay thanh chuoi mm:ss hoac hh:mm:ss."""
    seconds = int(seconds)
    if seconds < 3600:
        return "{:02d}:{:02d}".format(seconds // 60, seconds % 60)
    return "{:d}:{:02d}:{:02d}".format(
        seconds // 3600, (seconds % 3600) // 60, seconds % 60)

def countdown(msg, secs):
    """Hien thi dem nguoc co mau."""
    for i in range(int(secs), 0, -1):
        tprint("{}  {} {}{}s...{}".format(
            C.GRAY, msg, C.YELLOW, i, C.RESET))
        time.sleep(1)

# =============================================================================
# COS SIGNING
# =============================================================================

def _hmac_sha1(key, msg):
    """Tinh HMAC-SHA1."""
    return hmac_lib.new(key, msg.encode(), hashlib.sha1).hexdigest()

def build_cos_auth(sid, skey, method, pathname, clen):
    """Tao COS Authorization header (Tencent Cloud COS signing v5)."""
    now  = int(time.time())
    end  = now + 86400
    kt   = "{};{}".format(now, end)
    sk   = _hmac_sha1(skey.encode(), kt)
    hh   = "content-length={}&host={}".format(clen, COS_HOST)
    hs   = "{}\n{}\n\n{}\n".format(method.lower(), pathname, hh)
    hhttp = hashlib.sha1(hs.encode()).hexdigest()
    s2s  = "sha1\n{}\n{}\n".format(kt, hhttp)
    sig  = _hmac_sha1(sk.encode(), s2s)
    return ("q-sign-algorithm=sha1&q-ak={}"
            "&q-sign-time={}&q-key-time={}"
            "&q-header-list=content-length;host&q-url-param-list="
            "&q-signature={}").format(sid, kt, kt, sig)

# =============================================================================
# PARSE HAR  (v3.0: lay them encode_param, har_ua, har_sec_ch_ua)
# =============================================================================

def parse_har(har_path):
    """Parse file HAR de lay auth_token, encode_param, user_path, har_ua, har_sec_ch_ua.

    Tra ve: (auth_token, encode_param, user_path, har_ua, har_sec_ch_ua)
    Luon ghi de token/encodeparam → lay ban MOI NHAT.
    """
    try:
        with open(har_path, "r", encoding="utf-8", errors="ignore") as f:
            har = json.load(f)
    except json.JSONDecodeError as e:
        print(err("File HAR bi loi JSON: {} — {}".format(har_path, str(e)[:60])))
        return None, None, None, None, None
    except FileNotFoundError:
        print(err("Khong tim thay file: {}".format(har_path)))
        return None, None, None, None, None
    except OSError as e:
        print(err("Khong doc duoc file: {} — {}".format(har_path, str(e)[:60])))
        return None, None, None, None, None

    auth_token    = None
    encode_param  = None
    user_path     = None
    har_ua        = None
    har_sec_ch_ua = None

    # Duyet TAT CA entries — LUON ghi de → lay ban MOI NHAT
    for entry in har.get("log", {}).get("entries", []):
        req = entry["request"]
        url = req["url"]

        if "kgvn-api.mobagarena.com" in url and req.get("method") == "POST":
            hdrs = {h["name"].lower(): h["value"]
                    for h in req.get("headers", [])}
            if "msdk-itopencodeparam" in hdrs:
                auth_token = hdrs["msdk-itopencodeparam"]
            if "encodeparam" in hdrs:
                encode_param = hdrs["encodeparam"]
            if "user-agent" in hdrs:
                har_ua = hdrs["user-agent"]
            if "sec-ch-ua" in hdrs:
                har_sec_ch_ua = hdrs["sec-ch-ua"]

        if req["method"] == "PUT" and "myqcloud.com" in url and not user_path:
            path  = url.split(".myqcloud.com")[1].split("?")[0]
            parts = path.strip("/").split("/")
            if len(parts) >= 3:
                user_path = "/" + "/".join(parts[:3]) + "/"

    return auth_token, encode_param, user_path, har_ua, har_sec_ch_ua

# =============================================================================
# MEDIA PROCESSING
# =============================================================================

def resize_to_poster(img_bytes, target_w=POSTER_WIDTH, target_h=POSTER_HEIGHT):
    """Resize anh ve kich thuoc chuan poster (mac dinh 1080x1701).

    Su dung cover-crop: scale anh sao cho phu kin khung roi crop chinh giua.
    Giu chat luong cao voi LANCZOS resampling. Output la PNG bytes.
    Tra ve (png_bytes, did_resize, orig_size_str).
    """
    if not PILLOW_OK:
        # Khong co Pillow → tra ve nguyen ban
        return img_bytes, False, "?"

    try:
        img = _PIL_Image.open(io.BytesIO(img_bytes))
        orig_w, orig_h = img.size
        orig_str = "{}x{}".format(orig_w, orig_h)

        # Da dung kich thuoc chuan → khong can resize
        if orig_w == target_w and orig_h == target_h:
            return img_bytes, False, orig_str

        # Tinh ti le scale (cover: scale de phu kin khung)
        scale = max(target_w / orig_w, target_h / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        # Resize
        resample = getattr(_PIL_Image, 'LANCZOS',
                           getattr(_PIL_Image.Resampling, 'LANCZOS', 1))
        img = img.convert("RGBA")
        img = img.resize((new_w, new_h), resample)

        # Crop chinh giua
        left = (new_w - target_w) // 2
        top  = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))

        # Xuat PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        result = buf.getvalue()

        return result, True, orig_str

    except Exception as e:
        print(warn("    Resize loi: {} — giu nguyen ban".format(str(e)[:50])))
        return img_bytes, False, "?"


def prepare_media(file_path):
    """Doc va xu ly file media (JPG/PNG/WEBP/GIF/MP4).

    Tu dong resize anh tinh ve 1080x1701 (ti le chuan poster load tran).
    """
    file_path = Path(file_path)
    ext       = file_path.suffix.lower()
    raw       = file_path.read_bytes()

    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        resized, did_resize, orig_size = resize_to_poster(raw)
        if did_resize:
            print(info("    Resize: {} → {}x{}  ({:,}B → {:,}B)".format(
                orig_size, POSTER_WIDTH, POSTER_HEIGHT, len(raw), len(resized))))
        return {
            "png_bytes":  resized,
            "anim_bytes": None,
            "anim_ext":   None,
            "label":      "{} {:,}B{}".format(
                ext.upper().lstrip("."), len(resized),
                " (resized)" if did_resize else ""),
            "name":       file_path.name,
        }

    if ext == ".gif":
        if not PILLOW_OK:
            print(err("GIF can Pillow: pip install Pillow")); sys.exit(1)
        try:
            gif = _PIL_Image.open(io.BytesIO(raw))
            gif.seek(0)
            buf = io.BytesIO()
            gif.convert("RGBA").save(buf, format="PNG")
            png_b = buf.getvalue()
            # Resize frame dau ve kich thuoc chuan
            png_b, did_resize, orig_size = resize_to_poster(png_b)
            if did_resize:
                print(info("    GIF frame1 resize: {} → {}x{}".format(
                    orig_size, POSTER_WIDTH, POSTER_HEIGHT)))
            print(info("    GIF: frame1→PNG {:,}B  +  GIF goc {:,}B".format(
                len(png_b), len(raw))))
            return {
                "png_bytes":  png_b,
                "anim_bytes": raw,
                "anim_ext":   "gif",
                "label":      "GIF {:,}B anim".format(len(raw)),
                "name":       file_path.name,
            }
        except Exception as e:
            print(err("Loi GIF: " + str(e))); sys.exit(1)

    if ext == ".mp4":
        if not has_ffmpeg():
            print(err("MP4 can ffmpeg: pkg install ffmpeg")); sys.exit(1)
        try:
            tmp_dir = os.environ.get("TMPDIR", tempfile.gettempdir())
            tmp_mp4 = os.path.join(tmp_dir, "lt_tmp_{}.mp4".format(os.getpid()))
            tmp_gif = os.path.join(tmp_dir, "lt_tmp_{}.gif".format(os.getpid()))
            tmp_png = os.path.join(tmp_dir, "lt_tmp_{}.png".format(os.getpid()))

            with open(tmp_mp4, "wb") as f:
                f.write(raw)
            print(info("    MP4 → GIF (fps=10 scale=320)..."))
            subprocess.run(
                ["ffmpeg", "-i", tmp_mp4,
                 "-vf", "fps=10,scale=320:-1:flags=lanczos",
                 "-loop", "0", tmp_gif, "-y"],
                capture_output=True, check=True)
            with open(tmp_gif, "rb") as f:
                gif_b = f.read()
            subprocess.run(
                ["ffmpeg", "-i", tmp_gif, "-vframes", "1",
                 "-f", "image2", tmp_png, "-y"],
                capture_output=True, check=True)
            with open(tmp_png, "rb") as f:
                png_b = f.read()
            for fp in [tmp_mp4, tmp_gif, tmp_png]:
                try:
                    os.unlink(fp)
                except OSError:
                    pass
            print(info("    PNG render {:,}B  GIF anim {:,}B".format(
                len(png_b), len(gif_b))))
            return {
                "png_bytes":  png_b,
                "anim_bytes": gif_b,
                "anim_ext":   "gif",
                "label":      "MP4→GIF {:,}B anim".format(len(gif_b)),
                "name":       file_path.name,
            }
        except subprocess.CalledProcessError as e:
            print(err("ffmpeg that bai: " + str(e))); sys.exit(1)
        except Exception as e:
            print(err("Loi MP4: " + str(e))); sys.exit(1)

    print(err("Dinh dang khong ho tro: " + ext)); sys.exit(1)

def scan_media(directory):
    """Quet thu muc de tim cac file media ho tro."""
    files = sorted([
        p for p in Path(directory).iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ])
    if not files:
        print(err("Khong tim thay media trong: " + directory))
        sys.exit(1)
    return files

def find_har_files(directory="."):
    """Tim tat ca file .har trong thu muc."""
    return sorted(Path(directory).glob("*.har"))

# =============================================================================
# API HELPERS  (v3.0: encode_param, har_ua, har_sec_ch_ua, fresh sign)
# =============================================================================

def api_post(session, endpoint, payload, auth_token,
             encode_param=None, har_ua=None, har_sec_ch_ua=None,
             roleid="",
             retry_on_code1=False, max_retries=3, delay=3.0):
    """Gui POST request den API voi auth headers, sign bridge va retry logic."""
    hdrs = dict(FIXED_HEADERS)
    hdrs["content-type"]         = "application/json"
    hdrs["msdk-itopencodeparam"] = auth_token
    hdrs["traceparent"]          = gen_traceparent()
    hdrs["priority"]             = "u=1, i"
    hdrs["user-agent"]           = har_ua or DEFAULT_USER_AGENT
    hdrs["sec-ch-ua"]            = har_sec_ch_ua or DEFAULT_SEC_CH_UA
    data = {}
    for attempt in range(max_retries):
        # Tao encodeparam MOI cho MOI lan thu
        body_str = json.dumps(payload, separators=(',', ':'))
        ep = get_fresh_encodeparam(body_str, roleid, encode_param)
        if ep:
            hdrs["encodeparam"] = ep
        hdrs["traceparent"] = gen_traceparent()
        try:
            r = session.post(API_BASE + endpoint,
                             json=payload, headers=hdrs, timeout=API_TIMEOUT)
            try:
                data = r.json()
            except (ValueError, Exception):
                data = {"code": -1, "msg": "HTTP {} - {}".format(
                    r.status_code, r.text[:80])}
            if data is None:
                data = {"code": -1, "msg": "response body is null"}
            if r.status_code != 200:
                ep_info = "fresh" if (ep and ep != encode_param) else "HAR"
                tprint(warn("  HTTP {} tren {} [{}/{}] (ep={})".format(
                    r.status_code, endpoint.split('/')[-1],
                    attempt + 1, max_retries, ep_info)))
                if r.status_code == 403:
                    tprint(dim("  body: {}".format(str(data)[:100])))
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    continue
                return data
            if retry_on_code1 and data.get("code") == 1:
                wait = delay * (attempt + 1)
                tprint(warn("  code=1 thu lai {}s [{}/{}]".format(
                    int(wait), attempt + 1, max_retries)))
                time.sleep(wait)
                continue
            return data
        except requests.exceptions.ConnectionError as e:
            tprint(err("Loi ket noi: " + str(e)))
            return {"code": -1, "msg": str(e)}
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                tprint(warn("  Timeout [{}/{}] thu lai...".format(
                    attempt + 1, max_retries)))
                time.sleep(delay)
            else:
                return {"code": -1, "msg": "timeout"}
        except (ValueError,):
            tprint(warn("  Response khong phai JSON [{}/{}]".format(
                attempt + 1, max_retries)))
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                return {"code": -1, "msg": "invalid json response"}
    return data if data else {"code": -1, "msg": "max retries"}

def cos_put(session, url, data, headers, label=""):
    """Upload data len COS bucket voi retry."""
    for attempt in range(3):
        try:
            resp = session.put(url, data=data, headers=headers,
                               timeout=COS_UPLOAD_TIMEOUT)
            if resp.status_code == 200:
                return resp
            tprint(warn("  COS {} [{}]: {}".format(
                label, resp.status_code, resp.text[:120])))
            if attempt < 2:
                time.sleep(2)
        except requests.exceptions.ConnectionError as e:
            tprint(err("COS loi: " + str(e)))
            return None
    return resp

# =============================================================================
# BUILD picInfo  —  PLAYERIMAGE  (v3.0: giu nguyen stickerList rong)
# =============================================================================

def build_pic_info(pic_info_raw):
    """Tao picInfo payload cho saveposter."""
    bg = pic_info_raw.get("bg", {})
    return {
        "bg": {
            "id":     bg.get("id",     PI_BG_ID),
            "picUrl": bg.get("picUrl", PI_BG_PICURL),
            "source": 1,
            "width":  bg.get("width",  PI_BG_W),
            "height": bg.get("height", PI_BG_H),
            "posX":   bg.get("posX",   0),
            "posY":   bg.get("posY",   0),
        },
        "stickerList": [],
    }

# =============================================================================
# POSTER WORKER  (v3.0: sign bridge, COS creds rieng, savepostereditinfo)
# =============================================================================

def poster_worker(idx, acc_lbl, auth_token, encode_param, user_path,
                  media, pic_info_raw, is_share,
                  har_ua, har_sec_ch_ua, results):
    """Worker thread xu ly 1 poster."""
    tag     = "{}[{} P{:02d}]{}".format(
        C.CYAN+C.BOLD, acc_lbl[:14], idx, C.RESET)
    session = make_session()

    png_b    = media["png_bytes"]
    anim_b   = media["anim_bytes"]
    anim_ext = media["anim_ext"]
    fname    = media.get("name", "?")

    try:
        # A. createposter
        tprint("{} Tao poster {}...".format(tag, dim(fname[:18])))
        r = api_post(session, "/api/game/poster/playerimage/createposter",
                     {}, auth_token, encode_param, har_ua, har_sec_ch_ua)
        if r.get("code") != 0:
            tprint("{} {}".format(tag, err("createposter: " + r.get("msg", "")[:40])))
            results[idx-1] = (False, "createposter: " + r.get("msg", "")[:40])
            return
        pid = r["data"]["posterId"]
        tprint("{} PosterID={}{}{}".format(tag, C.YELLOW, pid, C.RESET))
        time.sleep(COS_UPLOAD_DELAY)

        # B. COS credentials — rieng cho tung file
        def get_creds(file_name, label=""):
            """Lay COS credentials cho 1 file upload."""
            rc = api_post(session, "/api/game/poster/getcoscredential",
                         {"scene": "PlayerimagePoster", "fileName": file_name},
                         auth_token, encode_param, har_ua, har_sec_ch_ua)
            if rc.get("code") != 0:
                tprint("{} {}".format(tag, err(
                    "getCos {} FAIL: {}".format(label, rc.get("msg", "")[:40]))))
                return None
            return rc.get("data")

        fn_png   = "0/1/{}.png".format(pid)
        fn_large = "0/1/{}_large.png".format(pid)

        def mkhdr(key, buf, creds_in):
            """Tao headers cho COS PUT request."""
            return {
                "Authorization":        build_cos_auth(
                    creds_in["tmpSecretId"], creds_in["tmpSecretKey"],
                    "PUT", key, len(buf)),
                "Content-Type":         "image/png",
                "Content-Length":       str(len(buf)),
                "Host":                 COS_HOST,
                "x-cos-security-token": creds_in["token"],
                "Origin":              "https://kgvn-camp.mobagarena.com",
                "Referer":             "https://kgvn-camp.mobagarena.com/",
            }

        # B1. Upload _large.png (creds rieng)
        tprint("{} COS credentials _large...".format(tag))
        creds_l = get_creds(fn_large, "_large")
        if creds_l:
            ck_l = creds_l.get("path", "{}{}".format(user_path, fn_large))
            r_l = cos_put(session, "https://" + COS_HOST + ck_l,
                          png_b, mkhdr(ck_l, png_b, creds_l), "_large")
            if r_l is not None and r_l.status_code == 200:
                tprint("{} COS _large {} {:,}B".format(tag, ok("OK"), len(png_b)))
            else:
                tprint("{} {}".format(tag, warn("COS _large FAIL")))
        time.sleep(CREDS_FETCH_DELAY)

        # B2. Upload .png (creds rieng)
        tprint("{} COS credentials .png...".format(tag))
        creds1 = get_creds(fn_png, ".png")
        if not creds1:
            tprint("{} {}".format(tag, err("getCOS .png FAIL")))
            results[idx-1] = (False, "getCOS .png fail")
            return
        ck = creds1.get("path", "{}{}".format(user_path, fn_png))
        r2 = cos_put(session, "https://" + COS_HOST + ck,
                     png_b, mkhdr(ck, png_b, creds1), ".png")
        if r2 is None or r2.status_code != 200:
            tprint("{} {}".format(tag, err("COS .png FAIL")))
            results[idx-1] = (False, "COS .png fail")
            return
        tprint("{} COS .png {} {:,}B".format(tag, ok("OK"), len(png_b)))

        cdn_host = creds1.get("cdnHost", CDN_UGC_BASE)
        sticker_url = cdn_host + ck

        # B3. GIF/MP4 animation upload (creds rieng)
        if anim_b is not None and anim_ext:
            fn_anim = "0/1/{}.{}".format(pid, anim_ext)
            creds_a = get_creds(fn_anim, "." + anim_ext)
            if creds_a:
                ck_a = creds_a.get("path", "{}{}".format(user_path, fn_anim))
                r_a = cos_put(session, "https://" + COS_HOST + ck_a,
                              anim_b, mkhdr(ck_a, anim_b, creds_a),
                              "." + anim_ext)
                if r_a is not None and r_a.status_code == 200:
                    sticker_url = cdn_host + ck_a
                    tprint("{} COS .{} {} {:,}B {}".format(
                        tag, anim_ext, ok("OK"), len(anim_b),
                        dim("(animation)")))
                else:
                    tprint("{} {}".format(
                        tag, warn(".{} FAIL → dung .png".format(anim_ext))))
            else:
                tprint("{} {}".format(
                    tag, warn("getCos .{} FAIL → dung .png".format(anim_ext))))

        time.sleep(COS_UPLOAD_DELAY)

        # C. savepostereditinfo (v3.0 NEW)
        pi = build_pic_info(pic_info_raw)
        rs = api_post(session,
                      "/api/game/poster/playerimage/savepostereditinfo",
                      {"picInfo": pi},
                      auth_token, encode_param, har_ua, har_sec_ch_ua,
                      retry_on_code1=True, max_retries=4, delay=4.0)
        tprint("{} editInfo {}".format(
            tag, ok("OK") if rs.get("code") == 0 else warn(
                "code={}".format(rs.get("code")))))
        time.sleep(SAVE_POSTER_DELAY)

        # D. saveposter
        pic_url = cdn_host + user_path

        rp = api_post(session,
                      "/api/game/poster/playerimage/saveposter",
                      {"posterId": pid, "isApply": True, "isShare": is_share,
                       "picUrl": pic_url, "picInfo": pi},
                      auth_token, encode_param, har_ua, har_sec_ch_ua,
                      retry_on_code1=True, max_retries=4, delay=4.0)

        unavail = rp.get("data", {}).get("unavailableResources", [])
        kind    = "{}GIF{}".format(C.CYAN, C.RESET) if anim_b else "IMG"

        if rp.get("code") == 0 and not unavail:
            tprint("{} {} ID={}{}{}  [{}]".format(
                tag, ok("THANH CONG"), C.GREEN, pid, C.RESET, kind))
            results[idx-1] = (True, pid, sticker_url, kind)
        elif rp.get("code") == 0:
            tprint("{} {} (co resource bi tu choi)".format(tag, ok("OK")))
            results[idx-1] = (True, pid, sticker_url, kind)
        else:
            tprint("{} {} {}".format(
                tag, err("THAT BAI"), rp.get("msg", "")[:40]))
            results[idx-1] = (False, "saveposter: " + rp.get("msg", "")[:40])

    except Exception as e:
        tprint("{} {}".format(tag, err("EXCEPTION: " + str(e)[:50])))
        results[idx-1] = (False, "exception: " + str(e)[:40])

# =============================================================================
# ACC WORKER  (v3.0: sign bridge init, encode_param)
# =============================================================================

def acc_worker(acc, media_list, rounds, is_share, acc_results):
    """Worker thread xu ly 1 account."""
    lbl = acc["label"]

    tprint("\n" + sep(62, "═", C.CYAN))
    tprint("{}{}  START  {}{}".format(C.CYAN+C.BOLD, "▶", lbl, C.RESET))
    tprint(sep(62, "═", C.CYAN))

    auth_token, encode_param, user_path, har_ua, har_sec_ch_ua = \
        parse_har(acc["har"])
    if not auth_token or not user_path:
        tprint(err("  [{}] Khong co token/path — bo qua".format(lbl)))
        acc_results[lbl] = {"ok": 0, "fail": 0, "rounds": []}
        return
    if not encode_param:
        tprint(warn("  [{}] Khong co encodeparam — co the bi 403".format(lbl)))

    # Init sign bridge
    sess = make_session()
    bridge_ok = init_sign_bridge_for_acc(
        sess, auth_token, encode_param, har_ua, har_sec_ch_ua)
    if not bridge_ok:
        tprint(warn("  [{}] Sign bridge init FAIL — dung encodeparam tu HAR".format(lbl)))

    tprint(dim("  Token   : {}...".format(auth_token[:35])))
    tprint(dim("  COS     : {}".format(user_path)))

    sess = make_session()

    # Lay picInfo hien tai
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

    n_media    = len(media_list)
    total_ok   = total_fail = 0
    round_logs = []

    for rnd in range(1, rounds + 1):
        tprint("")
        tprint("{}  [{}] Vong {:02d}/{:02d}  —  {} media song song{}".format(
            C.CYAN+C.BOLD, lbl[:16], rnd, rounds, n_media, C.RESET))

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

        ok_n   = sum(1 for res in results if res and res[0])
        fail_n = n_media - ok_n
        total_ok   += ok_n
        total_fail += fail_n
        round_logs.append((rnd, results))

        summary = "{} OK  {} FAIL".format(
            "{}{}{}".format(C.GREEN, ok_n,   C.RESET),
            "{}{}{}".format(C.RED,   fail_n, C.RESET))
        tprint("  {}[{}] Vong {:02d}: {}{}".format(
            C.BOLD, lbl[:16], rnd, summary, C.RESET))

        if rnd < rounds:
            tprint(dim("  [{}] Nghi {}s truoc vong tiep...".format(
                lbl[:16], ROUND_DELAY)))
            time.sleep(ROUND_DELAY)

    # Tong ket acc
    tprint("")
    tprint("{}┌─ DONE: {} {}".format(C.CYAN+C.BOLD, lbl, C.RESET))
    for rnd, results in round_logs:
        for i, res in enumerate(results, 1):
            g = (rnd - 1) * n_media + i
            if res and res[0]:
                kind = res[3] if len(res) > 3 else "?"
                tprint("{}│{}  V{:02d}#{:02d} {}  [{}]  ID={}".format(
                    C.CYAN, C.RESET, rnd, g, ok("OK"), kind, res[1]))
            else:
                msg = str(res[1])[:35] if res else "?"
                tprint("{}│{}  V{:02d}#{:02d} {}  {}".format(
                    C.CYAN, C.RESET, rnd, g, err("FAIL"), msg))
    tprint("{}└─ OK:{} {}{}{}  FAIL:{} {}{}{}  TONG:{}{}".format(
        C.CYAN,
        C.RESET, C.GREEN+C.BOLD, total_ok,   C.RESET,
        C.RESET, C.RED+C.BOLD,   total_fail, C.RESET,
        C.BOLD, rounds * n_media) + C.RESET)

    acc_results[lbl] = {"ok": total_ok, "fail": total_fail, "rounds": round_logs}

# =============================================================================
# BOOST WORKER  (v3.0 NEW)
# =============================================================================

def boost_worker(acc_lbl, auth_token, encode_param,
                 har_ua, har_sec_ch_ua,
                 poster_id, count, delay_s, boost_results):
    """Worker thread boost: tang luot dung nen."""
    session = make_session()
    tprint(info("[{}] Boost {}x  delay={}s".format(acc_lbl, count, delay_s)))
    ok_n = fail_n = 0
    for i in range(1, count + 1):
        r = api_post(session,
                     "/api/game/poster/playerimage/quickapplyposter",
                     {"posterId": poster_id},
                     auth_token, encode_param, har_ua, har_sec_ch_ua)
        if r.get("code") == 0:
            ok_n += 1
            tprint(ok("[{}][{}] OK  (tong={})".format(acc_lbl, i, ok_n)))
        else:
            fail_n += 1
            tprint(err("[{}][{}] FAIL  code={}  msg={}".format(
                acc_lbl, i, r.get("code"), r.get("msg", ""))))
            if fail_n >= 3:
                tprint(warn("[{}] 3 fail lien tiep — dung".format(acc_lbl)))
                break
        time.sleep(delay_s)
    tprint("{}[{}] Boost xong: {} ok  {} fail{}".format(
        C.BOLD, acc_lbl, ok_n, fail_n, C.RESET))
    boost_results[acc_lbl] = {"ok": ok_n, "fail": fail_n}

# =============================================================================
# MAIN
# =============================================================================

def run(har_path_arg, image_dir, rounds_arg, dry_run=False):
    """Ham chinh dieu phoi toan bo flow."""
    start_time = time.time()

    print("")
    print("{}{}".format(C.CYAN, "═"*62))
    print("{}  KGVN  Mod Anh Load Tran  ·  Multi-Account  v3.0     ".format(
        C.WHITE+C.BOLD))
    print("{}  JPG · PNG · WEBP · GIF · MP4  |  Sign Bridge  ".format(C.CYAN))
    print("{}{}".format(C.CYAN, "═"*62) + C.RESET)

    if dry_run:
        print("\n" + warn("CHE DO DRY-RUN: Chi kiem tra, KHONG upload"))

    print("\n" + info("Kiem tra ket noi..."))
    if not check_connectivity():
        print(err("Khong co ket noi internet!")); sys.exit(1)
    print(ok("Mang OK"))

    # ---- License check ----
    print("\n" + info("Kiem tra license..."))
    # License check bypassed
    global API_BASE
    API_BASE = 'https://kgvn-api.mobagarena.com'
#         print(info("Ma thiet bi (Device ID): {}".format(_0xD1())))
#         sys.exit(1)
#     API_BASE = _0xEP()

    # ---- Khoi dong Sign Bridge ----
    bridge_ok = start_sign_bridge()
    if not bridge_ok:
        print(warn("Sign bridge KHONG HOAT DONG."))
        print(warn("Se dung encodeparam tu HAR (co the bi -5001:auth failed)."))
        print(info("De fix: cai Node.js (pkg install nodejs) va dat sign_bridge.js cung thu muc."))

    # ---- Tim HAR ----
    use_one = (har_path_arg and har_path_arg != DEFAULT_HAR
               and os.path.exists(har_path_arg))
    if use_one:
        har_files = [Path(har_path_arg)]
    else:
        har_files = find_har_files(".")
        if not har_files and os.path.exists(DEFAULT_HAR):
            har_files = [Path(DEFAULT_HAR)]
    har_files = [h for h in har_files if h.exists()]

    if not har_files:
        print(err("Khong tim thay .har nao!")); sys.exit(1)

    # ---- Parse + hien thi ----
    print("\n" + bold("Phan tich {} file HAR:".format(len(har_files))))
    print("  {}{:<28}  {}{}".format(C.GRAY, "File", "Trang thai", C.RESET))
    print("  " + sep(50, "─", C.GRAY))
    acc_info = []
    for idx_h, h in enumerate(har_files, 1):
        tok, ep, upath, h_ua, h_sec = parse_har(str(h))
        status = ok("OK") if (tok and upath) else err("THIEU TOKEN/PATH")
        lbl    = h.stem
        ep_txt = dim(" [ep]") if ep else ""
        print("  {}{:02d}.{} {:<28}  {}{}".format(
            C.YELLOW, idx_h, C.RESET, h.name[:28], status, ep_txt))
        acc_info.append({
            "har": str(h), "token": tok, "encode_param": ep,
            "user_path": upath, "label": lbl,
            "har_ua": h_ua, "har_sec_ch_ua": h_sec,
        })

    valid = [a for a in acc_info if a["token"] and a["user_path"]]
    if not valid:
        print(err("Khong co acc nao hop le!")); sys.exit(1)

    # ---- Chon acc ----
    selected = valid
    if len(valid) > 1:
        print("")
        print("  {}Nhap 'all' / ENTER = dung TAT CA {} acc{}".format(
            C.CYAN, len(valid), C.RESET))
        print("  {}Nhap STT cach nhau (vd: 1 3) = chon rieng{}".format(
            C.GRAY, C.RESET))
        raw = cinput("  > ")
        if raw and raw.lower() != "all":
            try:
                idxs = [int(x) - 1 for x in raw.split()]
                sel  = [acc_info[i] for i in idxs
                        if 0 <= i < len(acc_info) and acc_info[i]["token"]]
                if sel:
                    selected = sel
                else:
                    print(warn("Khong hop le → Dung tat ca"))
            except Exception:
                print(warn("Nhap sai → Dung tat ca"))

    n_acc = len(selected)
    print("\n  {} acc se chay {}SONG SONG{}:".format(
        n_acc, C.CYAN+C.BOLD, C.RESET))
    for a in selected:
        print("    {}●{} {}".format(C.CYAN, C.RESET, a["label"]))

    # ---- Chon chuc nang ----
    main_mode = ask_choice(
        "Chon chuc nang:",
        {"1": "{}Mod media poster{} (JPG / PNG / GIF / MP4)".format(
            C.GREEN+C.BOLD, C.RESET),
         "2": "{}Tang luot dung nen{} (Boost)".format(
            C.YELLOW+C.BOLD, C.RESET)}
    )

    # ===========================================================
    # BOOST MODE
    # ===========================================================
    if main_mode == "2":
        print("\n" + bold("Nhap thong tin poster:"))
        poster_id = cinput("  PosterId  : ")
        try:
            count = int(cinput("  So lan    : "))
            d     = cinput("  Delay giay [mac dinh 1.0]: ")
            delay_s = float(d) if d else 1.0
        except ValueError:
            print(err("Nhap sai")); sys.exit(1)

        boost_results = {}
        threads = []
        for a in selected:
            tok, ep, upath, h_ua, h_sec = parse_har(a["har"])
            t = threading.Thread(
                target=boost_worker,
                args=(a["label"], tok, ep, h_ua, h_sec,
                      poster_id, count, delay_s, boost_results),
                daemon=True,
            )
            threads.append(t)

        print("\n" + bold("Bat dau boost {} acc SONG SONG...".format(n_acc)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        elapsed = time.time() - start_time
        print("\n" + sep(62, "═", C.CYAN))
        print("{}  BOOST TONG KET  ({} acc)  ⏱ {}{}".format(
            C.WHITE+C.BOLD, n_acc, format_duration(elapsed), C.RESET))
        print(sep(62, "─", C.GRAY))
        grand_ok = grand_fail = 0
        for lbl, res in boost_results.items():
            print("  {:<32}  {}OK:{:<5}{}  {}FAIL:{}{}".format(
                lbl[:32],
                C.GREEN, res["ok"],   C.RESET,
                C.RED,   res["fail"], C.RESET))
            grand_ok += res["ok"]
            grand_fail += res["fail"]
        print(sep(62, "─", C.GRAY))
        _0xD3(_0xD2() + 1)
        print("  {}TONG: OK={}  FAIL={}{}".format(
            C.BOLD, grand_ok, grand_fail, C.RESET))
        print(sep(62, "═", C.CYAN))
        return

    # ===========================================================
    # MOD POSTER MODE
    # ===========================================================

    # ---- Scan media ----
    print("\n" + info("Quet media trong: " + image_dir))
    all_files = scan_media(image_dir)
    print("  Tim thay {} file:".format(len(all_files)))
    TYPE_COLORS = {
        ".jpg":  "{}JPG{}".format(C.YELLOW, C.RESET),
        ".jpeg": "{}JPG{}".format(C.YELLOW, C.RESET),
        ".png":  "{}PNG{}".format(C.CYAN,   C.RESET),
        ".webp": "{}WEBP{}".format(C.CYAN,  C.RESET),
        ".gif":  "{}GIF{}".format(C.GREEN+C.BOLD, C.RESET),
        ".mp4":  "{}MP4{}".format(C.PURPLE+C.BOLD, C.RESET),
    }
    for i, p in enumerate(all_files, 1):
        tc = TYPE_COLORS.get(p.suffix.lower(), p.suffix.upper())
        print("  {}[{}]{}  {}  {}  {:.1f} KB".format(
            C.YELLOW, i, C.RESET, tc, p.name, p.stat().st_size / 1024))

    # ---- Phan cong anh ----
    if len(all_files) == 1:
        img_mode = "2"
        print("\n" + info("1 file duy nhat → tat ca acc dung chung."))
    else:
        if len(all_files) < n_acc:
            print("\n" + warn("{} file < {} acc — mode 1 se lap vong anh.".format(
                len(all_files), n_acc)))
        img_mode = ask_choice(
            "Che do phan cong media:",
            {"1": "Moi acc {}1 bo rieng{}  (acc1→file1, acc2→file2, ...)".format(
                C.BOLD, C.RESET),
             "2": "Tat ca acc dung {}chung{}  (toi da {} file/acc)".format(
                C.BOLD, C.RESET, MAX_MEDIA_PER_ACC)}
        )

    if img_mode == "1":
        print("\n  Phan cong (rieng):")
        for i, a in enumerate(selected):
            f = all_files[i % len(all_files)]
            print("    {}{}{}  →  {}".format(
                C.CYAN, a["label"][:30], C.RESET, f.name))
    else:
        shared = all_files[:MAX_MEDIA_PER_ACC]
        print("\n" + info("Dung chung {} file: {}".format(
            len(shared), ", ".join(p.name for p in shared))))

    # ---- Che do luu ----
    save_mode = ask_choice(
        "Che do LUU:",
        {"1": "{}Luu rieng{}  (chi minh toi dung)".format(C.CYAN, C.RESET),
         "2": "{}Quang truong{}  (moi nguoi thay)".format(C.YELLOW, C.RESET)}
    )
    is_share = (save_mode == "2")

    # ---- So vong ----
    if rounds_arg:
        rounds = max(1, rounds_arg)
    else:
        raw = cinput("\n  So vong lap (moi vong = {}s stagger/poster, ENTER=1): ".format(
            POSTER_STAGGER))
        try:
            rounds = int(raw) if raw else 1
            rounds = max(1, rounds)
        except ValueError:
            rounds = 1

    # ---- Pre-process media ----
    print("\n" + info("Xu ly media truoc khi chay..."))
    shared_media = None
    if img_mode == "2":
        shared_files = all_files[:MAX_MEDIA_PER_ACC]
        shared_media = []
        for p in shared_files:
            print(info("  Xu ly: {}".format(p.name)))
            shared_media.append(prepare_media(p))

    acc_media_map = {}
    for i, a in enumerate(selected):
        lbl = a["label"]
        if img_mode == "1":
            f = all_files[i % len(all_files)]
            print(info("  {} → {}".format(lbl[:25], f.name)))
            acc_media_map[lbl] = [prepare_media(f)]
        else:
            acc_media_map[lbl] = shared_media

    imgs_per    = len(shared_media) if img_mode == "2" else 1
    grand_total = rounds * imgs_per * n_acc
    print("\n  {} acc  ×  {} vong  ≈  {}{}{}  poster tong".format(
        n_acc, rounds, C.CYAN+C.BOLD, grand_total, C.RESET))
    print(dim("  Stagger poster: {}s  |  Delay vong: {}s  |  Stagger acc: {}s".format(
        POSTER_STAGGER, ROUND_DELAY, ACC_STAGGER)))

    # ---- Dry-run stop ----
    if dry_run:
        elapsed = time.time() - start_time
        print("\n" + sep(62, "═", C.CYAN))
        print("{}  DRY-RUN HOAN TAT  ({}){}".format(
            C.WHITE+C.BOLD, format_duration(elapsed), C.RESET))
        print(ok("Tat ca {} HAR hop le, {} media san sang.".format(
            len(valid), len(all_files))))
        print(info("Bo --dry-run de chay that.\n"))
        return

    # ---- Confirm ----
    confirm = cinput("\n  Nhap 'ok' de bat dau, Ctrl+C de huy: ")
    if confirm.lower() != "ok":
        print(err("Huy")); sys.exit(0)

    # ---- Spawn threads ----
    acc_results = {}
    threads     = []
    print("\n" + bold("Bat dau {} acc SONG SONG...".format(n_acc)))
    for a in selected:
        t = threading.Thread(
            target=acc_worker,
            args=(a, acc_media_map[a["label"]], rounds, is_share, acc_results),
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(ACC_STAGGER)

    for t in threads:
        t.join()

    # ---- Tong ket ----
    elapsed = time.time() - start_time
    print("")
    print(sep(62, "═", C.CYAN))
    print("{}  TONG KET  ({} acc song song)  ⏱ {}{}".format(
        C.WHITE+C.BOLD, n_acc, format_duration(elapsed), C.RESET))
    print(sep(62, "─", C.GRAY))
    grand_ok = grand_fail = 0
    for a in selected:
        res = acc_results.get(a["label"], {"ok": 0, "fail": 0})
        ok_a, fail_a = res["ok"], res["fail"]
        grand_ok += ok_a
        grand_fail += fail_a
        print("  {}{:<30}{}  {}OK:{:<4}{}  {}FAIL:{:<4}{}  TONG:{}".format(
            C.CYAN, a["label"][:30], C.RESET,
            C.GREEN, ok_a,   C.RESET,
            C.RED,   fail_a, C.RESET,
            ok_a + fail_a))
    print(sep(62, "─", C.GRAY))
    print("  {}TONG CONG:  OK={}{}{}  FAIL={}{}{}  /  {} poster{}".format(
        C.BOLD,
        C.GREEN, grand_ok,   C.RESET+C.BOLD,
        C.RED,   grand_fail, C.RESET+C.BOLD,
        grand_total, C.RESET))
    print(sep(62, "═", C.CYAN))
    _0xD3(_0xD2() + 1)
    print("\n  {}Mo game → Anh load tran de thay!{}\n".format(C.CYAN, C.RESET))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="KGVN Mod Anh Load Tran - Multi-Account Tool v3.0",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "TINH NANG:\n"
            "  * JPG / PNG / WEBP / GIF / MP4\n"
            "  * Dynamic encodeparam (Sign Bridge)\n"
            "  * Boost mode (tang luot dung nen)\n"
            "  * Acc chay song song dong thoi\n"
            "  * Auto-detect HAR files\n"
            "  * Dry-run mode de kiem tra truoc\n"
            "\nCAI DAT:\n"
            "  pip install requests Pillow\n"
            "  # Sign bridge: pkg install nodejs\n"
            "  # MP4: pkg install ffmpeg\n"
            "\nFILES CAN THIET (cung thu muc):\n"
            "  loadtran.py, sign_bridge.js, camp-security-oversea.0.1.0.js\n"
            "\nVI DU:\n"
            "  python loadtran.py\n"
            "  python loadtran.py --test-sign\n"
            "  python loadtran.py --rounds 3\n"
            "  python loadtran.py --dir /sdcard/DCIM\n"
            "  python loadtran.py --har acc1.har\n"
            "  python loadtran.py --dry-run\n"
        ),
    )
    ap.add_argument("--version", action="version",
                    version="%(prog)s " + __version__)
    ap.add_argument("--har",     default=DEFAULT_HAR,
                    help="File HAR cu the (mac dinh: auto-detect *.har)")
    ap.add_argument("--dir",     default=".",
                    help="Thu muc chua media (mac dinh: .)")
    ap.add_argument("--rounds",  type=int, default=None,
                    help="So vong lap")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chi kiem tra, khong upload")
    ap.add_argument("--test-sign", action="store_true",
                    help="Test sign bridge (Node.js) roi thoat")
    ap.add_argument("--auto", action="store_true",
                    help="Che do tu dong — nhap TK/MK, khong can HAR")
    ap.add_argument("--account", "-u", default=None,
                    help="Ten dang nhap Garena (dung voi --auto)")
    ap.add_argument("--password", "-p", default=None,
                    help="Mat khau Garena (dung voi --auto)")
    ap.add_argument("--accounts", "-a", default=None,
                    help="File JSON chua danh sach tai khoan (dung voi --auto)")
    args = ap.parse_args()

    if args.test_sign:
        print(bold("=== TEST SIGN BRIDGE ==="))
        ok_flag = start_sign_bridge()
        if ok_flag:
            print(ok("Sign bridge san sang!"))
            har_files = sorted(Path(".").glob("*.har"))
            if not har_files:
                print(err("Khong tim thay file .har de test"))
                stop_sign_bridge()
                sys.exit(1)
            h = har_files[0]
            print(info("Dung HAR: {}".format(h.name)))
            tok, ep, upath, h_ua, h_sec = parse_har(str(h))
            if not tok:
                print(err("Khong co token trong HAR"))
                stop_sign_bridge()
                sys.exit(1)
            sess = make_session()
            init_ok = init_sign_bridge_for_acc(sess, tok, ep, h_ua, h_sec)
            if init_ok:
                print(ok("Init OK! Thu tao 3 encodeparam..."))
                for i in range(3):
                    fresh_ep = get_fresh_encodeparam("{}", "")
                    if fresh_ep:
                        print(ok("  #{}: {} (len={})".format(
                            i+1, fresh_ep[:40]+"...", len(fresh_ep))))
                    else:
                        print(err("  #{}: FAIL".format(i+1)))
            else:
                print(err("Init FAIL!"))
                print(info("Token co the het han - capture HAR moi"))
        else:
            print(err("Sign bridge KHONG hoat dong!"))
            print(info("Kiem tra:"))
            print(info("  1. node --version"))
            print(info("  2. node sign_bridge.js --test"))
        stop_sign_bridge()
        sys.exit(0 if ok_flag else 1)

    if args.auto or args.accounts or args.account:
        try:
            from auto_loadtran import run_auto, load_accounts_file, input_accounts_interactive
            import getpass
            accounts = []
            if args.accounts:
                accounts = load_accounts_file(args.accounts)
                print(ok("Doc {} tai khoan tu {}".format(
                    len(accounts), args.accounts)))
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
            run_auto(accounts, args.dir, args.rounds, args.dry_run)
        except KeyboardInterrupt:
            print("\n" + err("Huy boi nguoi dung"))
        finally:
            stop_sign_bridge()
    else:
        try:
            run(args.har, args.dir, args.rounds, args.dry_run)
        finally:
            stop_sign_bridge()
