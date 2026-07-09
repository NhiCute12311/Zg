/**
 * Frida hook: libLogin.so - com/android/support/Login.Check bypass
 *
 * Phân tích:
 *   - Class: com/android/support/Login
 *   - Method: Check(Landroid/content/Context;Ljava/lang/String;)Ljava/lang/String;
 *   - Native impl: libLogin.so @ ARM offset 0x61C2C
 *   - Server: https://duymmo.io.vn/connect (HTTPS POST)
 *   - Return "OK" khi login thành công, chuỗi rỗng khi thất bại
 *
 * Patch logic:
 *   - Hook Java method trả về "OK" trực tiếp (không cần kết nối server)
 *   - Hoặc hook native để skip HTTP request
 */

'use strict';

Java.perform(function () {

    // ── Cách 1: Hook Java method (ưu tiên, đơn giản nhất) ──────────────────
    try {
        const Login = Java.use('com.android.support.Login');

        Login.Check.overload(
            'android.content.Context',
            'java.lang.String'
        ).implementation = function (ctx, token) {
            console.log('[Login.Check] Intercepted → returning "OK"');
            console.log('  token arg: ' + token);
            return 'OK';
        };
        console.log('[+] Hooked com.android.support.Login.Check (Java layer)');
    } catch (e) {
        console.log('[-] Java hook failed: ' + e + ' → trying native hook');
        hookNative();
    }

    // ── Cách 2: Hook native function ────────────────────────────────────────
    function hookNative() {
        const libBase = Module.findBaseAddress('libLogin.so');
        if (!libBase) {
            console.log('[-] libLogin.so not loaded yet, waiting...');
            return;
        }

        // Offset của hàm Check trong libLogin.so (ARM, không phải Thumb)
        const CHECK_OFFSET = 0x61C2C;
        const checkPtr = libBase.add(CHECK_OFFSET);

        // Offset của cờ thành công trong .bss (relative to load base)
        // Flag tại VMA 0x26E7E0; base address trong IDA là 0 → bss offset = 0x26E7E0
        // Nhưng khi load: base + 0x26E7E0 trỏ vào bss (run-time)

        Interceptor.attach(checkPtr, {
            onEnter: function (args) {
                this.env  = args[0];  // JNIEnv*
                this.thiz = args[1];  // jobject (unused)
                this.ctx  = args[2];  // Context
                this.str  = args[3];  // String token
                console.log('[Check] native onEnter');
            },
            onLeave: function (retval) {
                // Tạo Java String "OK" qua JNI để trả về
                const env = this.env;
                const NewStringUTF = new NativeFunction(
                    // JNIEnv->NewStringUTF offset 0x29C / 4 = 166
                    Memory.readPointer(Memory.readPointer(env).add(0x29C)),
                    'pointer', ['pointer', 'pointer']
                );
                const ok = Memory.allocUtf8String('OK');
                const jstr = NewStringUTF(env, ok);
                retval.replace(jstr);
                console.log('[Check] native return replaced with "OK"');
            }
        });
        console.log('[+] Hooked Check native @ ' + checkPtr);
    }
});

// ── Cách 3: Patch bit flag trong bộ nhớ sau khi SO load ──────────────────
//
// Khi libLogin.so được load, .bss offset 0x26E7E0 là cờ "login success".
// Nếu muốn patch trực tiếp:
//
//   const base = Module.findBaseAddress('libLogin.so');
//   const bssBase = 0x26E7E0;   // bss VMA trong IDA (base = 0)
//   // Tính offset thực: cần biết VMA của SO load
//   // Với PIE, base address thay đổi; dùng Module.findBaseAddress() + section offset
//   // Ví dụ nếu .bss thực là base + 0x26E7E0 thì:
//   Memory.writeU8(base.add(/* bss_offset_in_file */), 1);
//
// Lưu ý: cách này yêu cầu timing đúng sau khi SO load nhưng trước khi Check() gọi.
