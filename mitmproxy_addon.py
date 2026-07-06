"""
mitmproxy addon cho ZyGames - Bắt và log tất cả traffic.

Usage:
  mitmproxy -s mitmproxy_addon.py -p 8080 --ssl-insecure
  mitmdump -s mitmproxy_addon.py -p 8080 --ssl-insecure --set flow_detail=3

Trên device cần set proxy thành IP_MÁY:8080 và cài cert CA của mitmproxy.
Kết hợp với frida-ssl-bypass.js để bypass SSL pinning.
"""

import json
import os
import time
from datetime import datetime
from mitmproxy import ctx, http

LOG_DIR = "mitmproxy_captured"
TARGET_HOST = "zygame.gaqh8.fun"


class ZyGamesAddon:
    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.request_count = 0

    def request(self, flow: http.HTTPFlow):
        if TARGET_HOST not in (flow.request.pretty_host or ""):
            return

        self.request_count += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        req_data = {
            "timestamp": datetime.now().isoformat(),
            "count": self.request_count,
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "headers": dict(flow.request.headers),
            "body_text": None,
            "body_hex": None,
        }

        if flow.request.content:
            req_data["body_hex"] = flow.request.content.hex()
            try:
                req_data["body_text"] = flow.request.content.decode("utf-8")
            except UnicodeDecodeError:
                pass
            try:
                req_data["body_json"] = json.loads(flow.request.content)
            except (json.JSONDecodeError, TypeError):
                pass

        filepath = os.path.join(LOG_DIR, f"{timestamp}_REQ_{self.request_count}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(req_data, f, indent=2, ensure_ascii=False)

        ctx.log.info(f"[ZyGames] >>> {flow.request.method} {flow.request.pretty_url}")
        if flow.request.content:
            try:
                ctx.log.info(f"[ZyGames]     Body: {flow.request.content.decode()[:500]}")
            except UnicodeDecodeError:
                ctx.log.info(f"[ZyGames]     Body (hex): {flow.request.content[:100].hex()}")

    def response(self, flow: http.HTTPFlow):
        if TARGET_HOST not in (flow.request.pretty_host or ""):
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        resp_data = {
            "timestamp": datetime.now().isoformat(),
            "count": self.request_count,
            "status": flow.response.status_code,
            "url": flow.request.pretty_url,
            "headers": dict(flow.response.headers),
            "body_text": None,
            "body_hex": None,
        }

        if flow.response.content:
            resp_data["body_hex"] = flow.response.content.hex()
            try:
                resp_data["body_text"] = flow.response.content.decode("utf-8")
            except UnicodeDecodeError:
                pass
            try:
                resp_data["body_json"] = json.loads(flow.response.content)
            except (json.JSONDecodeError, TypeError):
                pass

        filepath = os.path.join(LOG_DIR, f"{timestamp}_RESP_{self.request_count}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(resp_data, f, indent=2, ensure_ascii=False)

        ctx.log.info(f"[ZyGames] <<< {flow.response.status_code} {flow.request.pretty_url}")
        if flow.response.content:
            try:
                ctx.log.info(f"[ZyGames]     Body: {flow.response.content.decode()[:500]}")
            except UnicodeDecodeError:
                ctx.log.info(f"[ZyGames]     Body (hex): {flow.response.content[:100].hex()}")


addons = [ZyGamesAddon()]
