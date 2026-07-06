#!/bin/bash
# Setup script cho ZyGames SSL Bypass + Fake Server
# Chạy trên máy tính (PC/Mac/Linux)

set -e

echo "=== ZyGames SSL Bypass Setup ==="

# 1. Tạo self-signed certificate
echo "[1/3] Generating SSL certificates..."
mkdir -p certs
if [ ! -f certs/server.key ]; then
    openssl req -x509 -newkey rsa:2048 \
        -keyout certs/server.key \
        -out certs/server.crt \
        -days 365 -nodes \
        -subj "/CN=zygame.gaqh8.fun" \
        -addext "subjectAltName=DNS:zygame.gaqh8.fun,DNS:localhost,IP:127.0.0.1"
    echo "  Certificates created in certs/"
else
    echo "  Certificates already exist"
fi

# 2. Tạo thư mục log
echo "[2/3] Creating log directories..."
mkdir -p captured_traffic
mkdir -p mitmproxy_captured

# 3. Kiểm tra dependencies
echo "[3/3] Checking dependencies..."
command -v python3 >/dev/null 2>&1 && echo "  python3: OK" || echo "  python3: MISSING (cần cài)"
command -v frida >/dev/null 2>&1 && echo "  frida: OK" || echo "  frida: MISSING (pip3 install frida-tools)"
command -v mitmproxy >/dev/null 2>&1 && echo "  mitmproxy: OK" || echo "  mitmproxy: OPTIONAL (pip3 install mitmproxy)"
command -v openssl >/dev/null 2>&1 && echo "  openssl: OK" || echo "  openssl: MISSING"

echo ""
echo "=== HƯỚNG DẪN SỬ DỤNG ==="
echo ""
echo "--- CÁCH 1: Frida + Fake Server (Khuyên dùng) ---"
echo ""
echo "Bước 1: Chạy fake server trên máy tính:"
echo "  python3 fake_server.py --mode proxy"
echo ""
echo "Bước 2: Sửa FAKE_SERVER_IP trong frida-ssl-bypass.js"
echo "  thành IP máy tính (vd: 192.168.1.100)"
echo ""
echo "Bước 3: Chạy Frida trên device:"
echo "  frida -U -f <package_name> -l frida-ssl-bypass.js --no-pause"
echo ""
echo "--- CÁCH 2: mitmproxy + Frida ---"
echo ""
echo "Bước 1: Chạy mitmproxy:"
echo "  mitmproxy -s mitmproxy_addon.py -p 8080 --ssl-insecure"
echo ""
echo "Bước 2: Set proxy trên device thành IP_MÁY:8080"
echo ""
echo "Bước 3: Chạy Frida SSL bypass:"
echo "  frida -U -f <package_name> -l frida-ssl-bypass.js --no-pause"
echo ""
echo "=== Logs sẽ được lưu trong captured_traffic/ ==="
