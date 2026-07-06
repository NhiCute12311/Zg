#!/usr/bin/env python3
"""
Fake Server cho ZyGames - MITM Proxy
Bắt tất cả request/response, forward tới real server hoặc trả response giả.

Usage:
  # Mode 1: MITM Proxy (forward tới real server, log tất cả)
  python3 fake_server.py --mode proxy

  # Mode 2: Standalone (trả response giả, không cần kết nối real server)
  python3 fake_server.py --mode standalone

  # Tạo self-signed cert
  python3 fake_server.py --generate-cert
"""

import argparse
import http.server
import json
import logging
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from http.server import HTTPServer

REAL_SERVER = "https://zygame.gaqh8.fun"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8443
LOG_DIR = "captured_traffic"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("fake_server.log")
    ]
)
logger = logging.getLogger("FakeServer")


def generate_self_signed_cert():
    cert_dir = "certs"
    os.makedirs(cert_dir, exist_ok=True)

    key_file = os.path.join(cert_dir, "server.key")
    cert_file = os.path.join(cert_dir, "server.crt")

    if os.path.exists(key_file) and os.path.exists(cert_file):
        logger.info("Certificates already exist")
        return key_file, cert_file

    logger.info("Generating self-signed certificate...")

    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", key_file,
        "-out", cert_file,
        "-days", "365",
        "-nodes",
        "-subj", f"/CN={REAL_SERVER.replace('https://', '').split('/')[0]}",
        "-addext", f"subjectAltName=DNS:{REAL_SERVER.replace('https://', '').split('/')[0]},DNS:localhost,IP:127.0.0.1"
    ], check=True)

    logger.info(f"Certificate: {cert_file}")
    logger.info(f"Key: {key_file}")
    return key_file, cert_file


def save_traffic(direction, path, headers, body, status=None):
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(LOG_DIR, f"{timestamp}_{direction}.json")

    data = {
        "timestamp": datetime.now().isoformat(),
        "direction": direction,
        "path": path,
        "headers": dict(headers) if headers else {},
        "body_hex": body.hex() if isinstance(body, bytes) else None,
        "body_text": None,
        "status": status
    }

    if body:
        try:
            data["body_text"] = body.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            pass
        try:
            data["body_json"] = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            pass

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filename


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """MITM Proxy - Forward requests to real server, log everything."""

    server_version = "nginx/1.18.0"
    mode = "proxy"

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_PUT(self):
        self._handle_request("PUT")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def do_OPTIONS(self):
        self._handle_request("OPTIONS")

    def _handle_request(self, method):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        logger.info("=" * 60)
        logger.info(f">>> REQUEST {method} {self.path}")
        logger.info(f"    Headers: {dict(self.headers)}")
        if body:
            try:
                logger.info(f"    Body: {body.decode('utf-8')[:2000]}")
            except UnicodeDecodeError:
                logger.info(f"    Body (hex): {body[:200].hex()}")

        save_traffic("REQUEST", f"{method} {self.path}", self.headers, body)

        if self.mode == "proxy":
            self._proxy_to_real_server(method, body)
        else:
            self._standalone_response(method, body)

    def _proxy_to_real_server(self, method, body):
        target_url = f"{REAL_SERVER}{self.path}"
        logger.info(f"    Forwarding to: {target_url}")

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(target_url, data=body if body else None, method=method)

            skip_headers = {"host", "content-length", "transfer-encoding", "connection"}
            for key, value in self.headers.items():
                if key.lower() not in skip_headers:
                    req.add_header(key, value)
            req.add_header("Host", REAL_SERVER.replace("https://", "").split("/")[0])

            response = urllib.request.urlopen(req, context=ctx, timeout=30)
            resp_body = response.read()
            resp_status = response.status
            resp_headers = dict(response.headers)

            logger.info(f"<<< RESPONSE {resp_status}")
            logger.info(f"    Headers: {resp_headers}")
            try:
                logger.info(f"    Body: {resp_body.decode('utf-8')[:2000]}")
            except UnicodeDecodeError:
                logger.info(f"    Body (hex): {resp_body[:200].hex()}")

            save_traffic("RESPONSE", self.path, response.headers, resp_body, status=resp_status)

            self.send_response(resp_status)
            for key, value in resp_headers.items():
                if key.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            resp_body = e.read()
            logger.info(f"<<< ERROR RESPONSE {e.code}")
            logger.info(f"    Body: {resp_body[:2000]}")
            save_traffic("RESPONSE_ERROR", self.path, dict(e.headers), resp_body, status=e.code)

            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        except Exception as e:
            logger.error(f"    Proxy error: {e}")
            error_resp = json.dumps({"error": str(e)}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_resp)))
            self.end_headers()
            self.wfile.write(error_resp)

    def _standalone_response(self, method, body):
        path = self.path.split("?")[0]

        if path == "/login.php":
            resp = {
                "code": 0,
                "msg": "success",
                "data": {
                    "token": "fake_token_" + str(int(time.time())),
                    "uid": 999999,
                    "server": "fake_server",
                    "timestamp": int(time.time())
                }
            }
        elif path.endswith(".php"):
            resp = {
                "code": 0,
                "msg": "ok",
                "data": {},
                "timestamp": int(time.time())
            }
        else:
            resp = {"code": 0, "msg": "ok"}

        resp_body = json.dumps(resp).encode()
        logger.info(f"<<< STANDALONE RESPONSE")
        logger.info(f"    Body: {resp_body.decode()}")

        save_traffic("RESPONSE_FAKE", self.path, {}, resp_body, status=200)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(resp_body)


def run_server(mode, host, port, use_ssl=True):
    handler = ProxyHandler
    handler.mode = mode

    server = HTTPServer((host, port), handler)

    if use_ssl:
        key_file, cert_file = generate_self_signed_cert()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_file, key_file)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        logger.info(f"HTTPS server ({mode} mode) listening on {host}:{port}")
    else:
        logger.info(f"HTTP server ({mode} mode) listening on {host}:{port}")

    logger.info(f"Real server: {REAL_SERVER}")
    logger.info(f"Traffic logs: ./{LOG_DIR}/")
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="ZyGames Fake Server / MITM Proxy")
    parser.add_argument("--mode", choices=["proxy", "standalone"], default="proxy",
                        help="proxy: forward to real server | standalone: fake responses")
    parser.add_argument("--host", default=LISTEN_HOST)
    parser.add_argument("--port", type=int, default=LISTEN_PORT)
    parser.add_argument("--no-ssl", action="store_true", help="Run without SSL (HTTP only)")
    parser.add_argument("--generate-cert", action="store_true", help="Generate certs and exit")

    args = parser.parse_args()

    if args.generate_cert:
        generate_self_signed_cert()
        return

    run_server(args.mode, args.host, args.port, use_ssl=not args.no_ssl)


if __name__ == "__main__":
    main()
