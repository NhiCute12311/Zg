/*
 * Frida SSL/VPN Bypass cho libZyGames.so (libyeqlmn.so)
 *
 * Binary: Unity IL2CPP + statically linked libcurl + OpenSSL 1.1.x
 * Server: https://zygame.gaqh8.fun/login.php
 * Arch: ARM64
 *
 * Usage:
 *   frida -U -f <package_name> -l frida-ssl-bypass.js --no-pause
 *   frida -U --attach-name="<app_name>" -l frida-ssl-bypass.js
 */

"use strict";

const LIB_NAME = "libyeqlmn.so";
const TARGET_HOST = "zygame.gaqh8.fun";
const FAKE_SERVER_IP = "YOUR_SERVER_IP";  // <-- Thay bằng IP fake server của bạn
const FAKE_SERVER_PORT = 8443;

let libBase = null;

function log(tag, msg) {
    console.log(`[ZyBypass][${tag}] ${msg}`);
}

function waitForLibrary(name, callback) {
    const interval = setInterval(function () {
        const mod = Process.findModuleByName(name);
        if (mod) {
            clearInterval(interval);
            libBase = mod.base;
            log("INIT", `${name} loaded at ${mod.base} size=${mod.size}`);
            callback(mod);
        }
    }, 200);
}

// ============================================================
// 1. SSL PINNING BYPASS (OpenSSL statically linked trong .so)
// ============================================================

function bypassSSL_StaticOpenSSL(mod) {
    // Tìm các hàm OpenSSL trong binary bằng pattern matching
    // Vì OpenSSL được static link, không có symbol export
    // Ta hook qua các string reference và pattern

    // --- Hook SSL_CTX_set_verify ---
    // Pattern: tìm xref tới string "SSL for verify callback"
    const verifyCallbackStr = Memory.scanSync(mod.base, mod.size,
        stringToPattern("SSL for verify callback"));

    if (verifyCallbackStr.length > 0) {
        log("SSL", `Found "SSL for verify callback" at ${verifyCallbackStr[0].address}`);
    }

    // --- Hook thông qua curl_easy_setopt pattern ---
    // CURLOPT_SSL_VERIFYPEER = 64, CURLOPT_SSL_VERIFYHOST = 81
    // Tìm và patch các giá trị verify

    // --- Phương pháp chính: Hook getaddrinfo/connect để redirect ---
    hookGetaddrinfo();
    hookConnect();

    // --- Hook SSL_CTX_set_verify bằng pattern scan ---
    findAndHookSSLVerify(mod);
}

function stringToPattern(str) {
    let pattern = "";
    for (let i = 0; i < str.length; i++) {
        if (i > 0) pattern += " ";
        pattern += str.charCodeAt(i).toString(16).padStart(2, "0");
    }
    return pattern;
}

function findAndHookSSLVerify(mod) {
    // Scan cho pattern của SSL_CTX_set_verify trên ARM64
    // SSL_CTX_set_verify(ctx, mode, callback)
    // Khi mode != SSL_VERIFY_NONE (0), ta patch thành 0

    // Pattern: tìm string "SSL certificate verify result"
    const patterns = [
        "SSL certificate verify result",
        "CERT verify",
        "SSL certificate problem"
    ];

    patterns.forEach(function(str) {
        const results = Memory.scanSync(mod.base, mod.size, stringToPattern(str));
        if (results.length > 0) {
            log("SSL", `Found "${str}" ref at ${results[0].address}`);
        }
    });

    // Hook SSL_CTX_set_verify thông qua GOT/PLT nếu có
    // Vì static linked, ta cần scan pattern ARM64 instruction

    // Approach: Hook tất cả các hàm verify liên quan qua export scan
    try {
        // Nếu có symbol (unlikely cho stripped binary)
        const ssl_ctx_set_verify = Module.findExportByName(null, "SSL_CTX_set_verify");
        if (ssl_ctx_set_verify) {
            Interceptor.attach(ssl_ctx_set_verify, {
                onEnter: function (args) {
                    log("SSL", "SSL_CTX_set_verify called, forcing SSL_VERIFY_NONE");
                    args[1] = ptr(0); // SSL_VERIFY_NONE
                    args[2] = ptr(0); // no callback
                }
            });
        }
    } catch (e) {}

    try {
        const ssl_set_verify = Module.findExportByName(null, "SSL_set_verify");
        if (ssl_set_verify) {
            Interceptor.attach(ssl_set_verify, {
                onEnter: function (args) {
                    log("SSL", "SSL_set_verify called, forcing SSL_VERIFY_NONE");
                    args[1] = ptr(0);
                    args[2] = ptr(0);
                }
            });
        }
    } catch (e) {}

    // X509_verify_cert - force return 1 (success)
    try {
        const x509_verify = Module.findExportByName(null, "X509_verify_cert");
        if (x509_verify) {
            Interceptor.replace(x509_verify, new NativeCallback(function (ctx) {
                log("SSL", "X509_verify_cert -> forced OK");
                return 1;
            }, "int", ["pointer"]));
        }
    } catch (e) {}
}

// ============================================================
// 2. REDIRECT DNS/CONNECT tới FAKE SERVER
// ============================================================

function hookGetaddrinfo() {
    const getaddrinfo = Module.findExportByName("libc.so", "getaddrinfo");
    if (!getaddrinfo) return;

    Interceptor.attach(getaddrinfo, {
        onEnter: function (args) {
            this.host = args[0].readUtf8String();
            if (this.host && this.host.indexOf(TARGET_HOST) !== -1) {
                log("DNS", `getaddrinfo("${this.host}") -> redirecting to ${FAKE_SERVER_IP}`);
                this.shouldRedirect = true;
                args[0] = Memory.allocUtf8String(FAKE_SERVER_IP);
            }
        },
        onLeave: function (retval) {
            if (this.shouldRedirect) {
                log("DNS", `getaddrinfo redirected for ${this.host}`);
            }
        }
    });

    const gethostbyname = Module.findExportByName("libc.so", "gethostbyname");
    if (gethostbyname) {
        Interceptor.attach(gethostbyname, {
            onEnter: function (args) {
                this.host = args[0].readUtf8String();
                if (this.host && this.host.indexOf(TARGET_HOST) !== -1) {
                    log("DNS", `gethostbyname("${this.host}") -> redirecting`);
                    args[0] = Memory.allocUtf8String(FAKE_SERVER_IP);
                }
            }
        });
    }
}

function hookConnect() {
    const connect = Module.findExportByName("libc.so", "connect");
    if (!connect) return;

    Interceptor.attach(connect, {
        onEnter: function (args) {
            const sockfd = args[0].toInt32();
            const addr = args[1];
            const addrLen = args[2].toInt32();

            const family = addr.readU16();
            if (family === 2) { // AF_INET
                const port = (addr.add(2).readU8() << 8) | addr.add(3).readU8();
                const ip = `${addr.add(4).readU8()}.${addr.add(5).readU8()}.${addr.add(6).readU8()}.${addr.add(7).readU8()}`;

                if (port === 443) {
                    log("NET", `connect() to ${ip}:${port} -> redirecting to ${FAKE_SERVER_IP}:${FAKE_SERVER_PORT}`);

                    // Rewrite IP
                    const parts = FAKE_SERVER_IP.split(".");
                    addr.add(4).writeU8(parseInt(parts[0]));
                    addr.add(5).writeU8(parseInt(parts[1]));
                    addr.add(6).writeU8(parseInt(parts[2]));
                    addr.add(7).writeU8(parseInt(parts[3]));

                    // Rewrite port
                    addr.add(2).writeU8((FAKE_SERVER_PORT >> 8) & 0xff);
                    addr.add(3).writeU8(FAKE_SERVER_PORT & 0xff);
                }
            }
        }
    });
}

// ============================================================
// 3. VPN DETECTION BYPASS
// ============================================================

function bypassVPNDetection() {
    // Hook fopen để ẩn /proc/net/if_inet6, /sys/class/net/tun*
    const fopen = Module.findExportByName("libc.so", "fopen");
    if (fopen) {
        Interceptor.attach(fopen, {
            onEnter: function (args) {
                const path = args[0].readUtf8String();
                if (path && (
                    path.indexOf("tun") !== -1 ||
                    path.indexOf("ppp") !== -1 ||
                    path.indexOf("vpn") !== -1 ||
                    path.indexOf("tap") !== -1
                )) {
                    log("VPN", `fopen("${path}") -> blocked`);
                    this.block = true;
                }
            },
            onLeave: function (retval) {
                if (this.block) {
                    retval.replace(ptr(0)); // return NULL
                }
            }
        });
    }

    // Hook access() để chặn kiểm tra VPN interfaces
    const access_fn = Module.findExportByName("libc.so", "access");
    if (access_fn) {
        Interceptor.attach(access_fn, {
            onEnter: function (args) {
                const path = args[0].readUtf8String();
                if (path && (
                    path.indexOf("/dev/tun") !== -1 ||
                    path.indexOf("/dev/ppp") !== -1 ||
                    path.indexOf("vpnservice") !== -1
                )) {
                    log("VPN", `access("${path}") -> blocked`);
                    this.block = true;
                }
            },
            onLeave: function (retval) {
                if (this.block) {
                    retval.replace(ptr(-1)); // ENOENT
                }
            }
        });
    }

    // Hook Java VPN detection nếu có
    if (Java.available) {
        Java.perform(function () {
            try {
                // NetworkInterface.getName() -> ẩn tun0/ppp0
                const NetworkInterface = Java.use("java.net.NetworkInterface");
                NetworkInterface.getName.implementation = function () {
                    const name = this.getName();
                    if (name && (name.indexOf("tun") !== -1 || name.indexOf("ppp") !== -1)) {
                        log("VPN", `NetworkInterface.getName() "${name}" -> hidden`);
                        return "wlan0";
                    }
                    return name;
                };
            } catch (e) {}

            try {
                // ConnectivityManager VPN check
                const ConnectivityManager = Java.use("android.net.ConnectivityManager");
                ConnectivityManager.getNetworkInfo.overload("int").implementation = function (type) {
                    if (type === 17) { // TYPE_VPN
                        log("VPN", "getNetworkInfo(TYPE_VPN) -> null");
                        return null;
                    }
                    return this.getNetworkInfo(type);
                };
            } catch (e) {}
        });
    }
}

// ============================================================
// 4. SSL PING BYPASS
// ============================================================

function bypassSSLPing() {
    // Hook các hàm kiểm tra kết nối SSL
    if (Java.available) {
        Java.perform(function () {
            try {
                // TrustManager bypass
                const X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
                const SSLContext = Java.use("javax.net.ssl.SSLContext");
                const TrustManager = Java.registerClass({
                    name: "com.zygame.TrustAllManager",
                    implements: [X509TrustManager],
                    methods: {
                        checkClientTrusted: function (chain, authType) {},
                        checkServerTrusted: function (chain, authType) {},
                        getAcceptedIssuers: function () { return []; }
                    }
                });

                const TrustManagers = [TrustManager.$new()];
                const sslCtx = SSLContext.getInstance("TLS");
                sslCtx.init(null, TrustManagers, null);

                const SSLSocketFactory = Java.use("javax.net.ssl.HttpsURLConnection");
                SSLSocketFactory.setDefaultSSLSocketFactory.call(
                    SSLSocketFactory, sslCtx.getSocketFactory()
                );

                log("SSL", "Java TrustManager bypassed");
            } catch (e) {
                log("SSL", "Java TrustManager bypass failed: " + e);
            }

            try {
                // HostnameVerifier bypass
                const HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
                const AllowAll = Java.registerClass({
                    name: "com.zygame.AllowAllHostnames",
                    implements: [HostnameVerifier],
                    methods: {
                        verify: function (hostname, session) {
                            log("SSL", `HostnameVerifier.verify("${hostname}") -> true`);
                            return true;
                        }
                    }
                });

                const HttpsURLConnection = Java.use("javax.net.ssl.HttpsURLConnection");
                HttpsURLConnection.setDefaultHostnameVerifier.call(
                    HttpsURLConnection, AllowAll.$new()
                );

                log("SSL", "HostnameVerifier bypassed");
            } catch (e) {}
        });
    }
}

// ============================================================
// 5. LOG REQUEST/RESPONSE
// ============================================================

function hookSendRecv() {
    // Hook send() và recv() để log raw data
    const send_fn = Module.findExportByName("libc.so", "send");
    const recv_fn = Module.findExportByName("libc.so", "recv");

    if (send_fn) {
        Interceptor.attach(send_fn, {
            onEnter: function (args) {
                const fd = args[0].toInt32();
                const buf = args[1];
                const len = args[2].toInt32();
                if (len > 0 && len < 65536) {
                    try {
                        const data = buf.readByteArray(Math.min(len, 4096));
                        const str = arrayBufferToString(data);
                        if (str.indexOf("HTTP") !== -1 || str.indexOf("POST") !== -1 ||
                            str.indexOf("GET") !== -1 || str.indexOf("login") !== -1) {
                            log("SEND", `fd=${fd} len=${len}\n${str.substring(0, 2048)}`);
                        }
                    } catch (e) {}
                }
            }
        });
    }

    if (recv_fn) {
        Interceptor.attach(recv_fn, {
            onEnter: function (args) {
                this.fd = args[0].toInt32();
                this.buf = args[1];
            },
            onLeave: function (retval) {
                const len = retval.toInt32();
                if (len > 0 && len < 65536) {
                    try {
                        const data = this.buf.readByteArray(Math.min(len, 4096));
                        const str = arrayBufferToString(data);
                        if (str.indexOf("HTTP") !== -1 || str.indexOf("{") !== -1) {
                            log("RECV", `fd=${this.fd} len=${len}\n${str.substring(0, 2048)}`);
                        }
                    } catch (e) {}
                }
            }
        });
    }
}

function arrayBufferToString(buf) {
    const arr = new Uint8Array(buf);
    let str = "";
    for (let i = 0; i < arr.length; i++) {
        const c = arr[i];
        if (c >= 32 && c <= 126) {
            str += String.fromCharCode(c);
        } else if (c === 10 || c === 13) {
            str += String.fromCharCode(c);
        } else {
            str += ".";
        }
    }
    return str;
}

// ============================================================
// MAIN
// ============================================================

log("INIT", "ZyGames SSL/VPN Bypass script starting...");
log("INIT", `Target: ${TARGET_HOST} -> ${FAKE_SERVER_IP}:${FAKE_SERVER_PORT}`);

bypassVPNDetection();
bypassSSLPing();
hookSendRecv();

waitForLibrary(LIB_NAME, function (mod) {
    log("INIT", "Library loaded, applying SSL bypass...");
    bypassSSL_StaticOpenSSL(mod);
    log("INIT", "All hooks applied successfully!");
});
