/*
 * Frida Traffic Logger cho libZyGames.so (đã patch SSL)
 *
 * Dùng KẾT HỢP với file .so đã patch để log requests/responses.
 * Không cần bypass SSL nữa vì đã patch trực tiếp trong binary.
 *
 * Usage:
 *   frida -U -f <package_name> -l frida_hook_traffic.js --no-pause
 */

"use strict";

const LIB_NAME = "libyeqlmn.so";

// curl_easy_setopt tại offset 0xbad958 trong .so
const CURL_EASY_SETOPT_OFFSET = 0xbad958;

// CURLOPT constants
const CURLOPT_URL = 10002;
const CURLOPT_POSTFIELDS = 10015;
const CURLOPT_SSL_VERIFYPEER = 64;
const CURLOPT_SSL_VERIFYHOST = 81;
const CURLOPT_WRITEFUNCTION = 10001;

function log(tag, msg) {
    console.log(`[ZyHook][${tag}] ${msg}`);
}

function hookCurlEasySetopt(mod) {
    const setopt = mod.base.add(CURL_EASY_SETOPT_OFFSET);
    log("CURL", `Hooking curl_easy_setopt at ${setopt}`);

    Interceptor.attach(setopt, {
        onEnter: function (args) {
            const handle = args[0];
            const option = args[1].toInt32();

            if (option === CURLOPT_URL) {
                try {
                    const url = args[2].readUtf8String();
                    log("URL", url);
                } catch (e) {}
            } else if (option === CURLOPT_POSTFIELDS) {
                try {
                    const postData = args[2].readUtf8String();
                    log("POST", postData ? postData.substring(0, 2000) : "(empty)");
                } catch (e) {
                    try {
                        const postData = args[2].readByteArray(256);
                        log("POST", hexdump(postData, { length: 256 }));
                    } catch (e2) {}
                }
            } else if (option === CURLOPT_SSL_VERIFYPEER) {
                const val = args[2].toInt32();
                log("SSL", `VERIFYPEER = ${val}` + (val === 0 ? " (DISABLED)" : " (ENABLED)"));
            } else if (option === CURLOPT_SSL_VERIFYHOST) {
                const val = args[2].toInt32();
                log("SSL", `VERIFYHOST = ${val}` + (val === 0 ? " (DISABLED)" : " (ENABLED)"));
            }
        }
    });
}

function hookSendRecv() {
    const send_fn = Module.findExportByName("libc.so", "send");
    const recv_fn = Module.findExportByName("libc.so", "recv");
    const write_fn = Module.findExportByName("libc.so", "write");
    const read_fn = Module.findExportByName("libc.so", "read");

    // Track SSL FDs
    const sslFds = new Set();

    if (send_fn) {
        Interceptor.attach(send_fn, {
            onEnter: function (args) {
                const fd = args[0].toInt32();
                const buf = args[1];
                const len = args[2].toInt32();
                if (len > 0 && len < 65536) {
                    try {
                        const peek = buf.readByteArray(Math.min(len, 4));
                        const first4 = new Uint8Array(peek);
                        // Detect HTTP or TLS
                        if ((first4[0] === 0x47 || first4[0] === 0x50 || first4[0] === 0x48) &&
                            first4[1] >= 0x20 && first4[1] < 0x7f) {
                            // HTTP plaintext
                            const data = buf.readUtf8String(Math.min(len, 4096));
                            log("SEND", `fd=${fd} len=${len}\n${data}`);
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
                this.reqLen = args[2].toInt32();
            },
            onLeave: function (retval) {
                const len = retval.toInt32();
                if (len > 0 && len < 65536) {
                    try {
                        const peek = this.buf.readByteArray(Math.min(len, 4));
                        const first4 = new Uint8Array(peek);
                        if ((first4[0] === 0x48 && first4[1] === 0x54) ||
                            first4[0] === 0x7b) {
                            const data = this.buf.readUtf8String(Math.min(len, 4096));
                            log("RECV", `fd=${this.fd} len=${len}\n${data}`);
                        }
                    } catch (e) {}
                }
            }
        });
    }
}

// Hook SSL_read/SSL_write cho encrypted traffic
function hookSSLReadWrite(mod) {
    // Tìm SSL_read và SSL_write trong static linked OpenSSL
    // Chúng được gọi qua function pointer trong curl
    // Thay vào đó, hook ở level cao hơn: curl write callback

    // Hook connect() để biết khi nào kết nối mới được tạo
    const connect_fn = Module.findExportByName("libc.so", "connect");
    if (connect_fn) {
        Interceptor.attach(connect_fn, {
            onEnter: function (args) {
                const addr = args[1];
                const family = addr.readU16();
                if (family === 2) { // AF_INET
                    const port = (addr.add(2).readU8() << 8) | addr.add(3).readU8();
                    const ip = `${addr.add(4).readU8()}.${addr.add(5).readU8()}.${addr.add(6).readU8()}.${addr.add(7).readU8()}`;
                    if (port === 443 || port === 80 || port === 8443) {
                        log("CONNECT", `${ip}:${port}`);
                    }
                }
            }
        });
    }
}

function waitForLibrary(name, callback) {
    const interval = setInterval(function () {
        const mod = Process.findModuleByName(name);
        if (mod) {
            clearInterval(interval);
            log("INIT", `${name} loaded at ${mod.base} size=${mod.size}`);
            callback(mod);
        }
    }, 200);
}

log("INIT", "ZyGames Traffic Logger starting...");
hookSendRecv();

waitForLibrary(LIB_NAME, function (mod) {
    hookCurlEasySetopt(mod);
    hookSSLReadWrite(mod);
    log("INIT", "All hooks applied!");
});
