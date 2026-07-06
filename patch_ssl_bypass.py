#!/usr/bin/env python3
"""
SSL Bypass Patcher cho libZyGames.so (SONAME: libyeqlmn.so)

Binary info:
  - Arch: ARM64 (aarch64), Android
  - Engine: Unity IL2CPP
  - Networking: statically linked libcurl + OpenSSL 1.1.x
  - Server: https://zygame.gaqh8.fun/login.php

Patches applied:
  1. CURLOPT_SSL_VERIFYPEER = 1 -> 0  (disable SSL certificate verification)
  2. CURLOPT_SSL_VERIFYHOST = 2 -> 0  (disable hostname verification)
  3. Dynamic VERIFYHOST calculation -> force 0
  4. Dynamic VERIFYPEER calculation -> force 0
  5. OpenSSL SSL_CTX_set_verify mode -> force SSL_VERIFY_NONE (0)

Usage:
  python3 patch_ssl_bypass.py libZyGames.so
  python3 patch_ssl_bypass.py libZyGames.so -o libZyGames_patched.so
"""

import argparse
import hashlib
import os
import shutil
import struct
import sys


PATCHES = [
    {
        "offset": 0x74c44c,
        "original": 0x52800022,  # mov w2, #0x1
        "patched":  0x52800002,  # mov w2, #0x0
        "description": "curl_easy_setopt(CURLOPT_SSL_VERIFYPEER, 1) -> 0",
    },
    {
        "offset": 0x74c460,
        "original": 0x52800042,  # mov w2, #0x2
        "patched":  0x52800002,  # mov w2, #0x0
        "description": "curl_easy_setopt(CURLOPT_SSL_VERIFYHOST, 2) -> 0",
    },
    {
        "offset": 0xb8a564,
        "original": 0x927f0102,  # and x2, x8, #0x2
        "patched":  0xaa1f03e2,  # mov x2, xzr
        "description": "Dynamic VERIFYHOST value -> force 0",
    },
    {
        "offset": 0xb8a5a0,
        "original": 0xd373cd02,  # ubfx x2, x8, #51, #1
        "patched":  0xaa1f03e2,  # mov x2, xzr
        "description": "Dynamic VERIFYPEER value -> force 0",
    },
    {
        "offset": 0xbf29d4,
        "original": 0x1a890174,  # csel w20, w11, w9, eq
        "patched":  0x2a1f03f4,  # mov w20, wzr  (SSL_VERIFY_NONE = 0)
        "description": "OpenSSL SSL_CTX_set_verify mode -> SSL_VERIFY_NONE",
    },
]


def read_u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def write_u32(data, offset, value):
    struct.pack_into("<I", data, offset, value)


def patch_binary(input_path, output_path):
    with open(input_path, "rb") as f:
        data = bytearray(f.read())

    original_md5 = hashlib.md5(data).hexdigest()
    print(f"Input: {input_path}")
    print(f"Size: {len(data)} bytes ({len(data)/1024/1024:.1f} MB)")
    print(f"MD5: {original_md5}")
    print()

    applied = 0
    skipped = 0

    for p in PATCHES:
        offset = p["offset"]
        expected = p["original"]
        new_val = p["patched"]
        desc = p["description"]

        actual = read_u32(data, offset)

        if actual == expected:
            write_u32(data, offset, new_val)
            applied += 1
            print(f"  [PATCHED] 0x{offset:08x}: 0x{expected:08x} -> 0x{new_val:08x}")
            print(f"            {desc}")
        elif actual == new_val:
            skipped += 1
            print(f"  [SKIP]    0x{offset:08x}: already patched")
        else:
            print(f"  [ERROR]   0x{offset:08x}: unexpected value 0x{actual:08x}")
            print(f"            expected 0x{expected:08x}, got 0x{actual:08x}")
            print(f"            This binary version may be different!")
            return False

    print()
    print(f"Applied: {applied}, Skipped: {skipped}, Total: {len(PATCHES)}")

    if applied > 0:
        patched_md5 = hashlib.md5(data).hexdigest()
        with open(output_path, "wb") as f:
            f.write(data)
        os.chmod(output_path, 0o755)
        print(f"\nOutput: {output_path}")
        print(f"MD5: {patched_md5}")
        print("\nDone! Replace the original .so file in the APK with the patched one.")
    else:
        print("\nNo patches needed (all already applied).")

    return True


def main():
    parser = argparse.ArgumentParser(description="SSL Bypass Patcher for libZyGames.so")
    parser.add_argument("input", help="Path to original libZyGames.so")
    parser.add_argument("-o", "--output", help="Output path (default: <input>_patched.so)")
    parser.add_argument("--verify-only", action="store_true", help="Only verify, don't patch")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        sys.exit(1)

    if args.verify_only:
        with open(args.input, "rb") as f:
            data = f.read()
        print("=== Verification ===")
        for p in PATCHES:
            actual = read_u32(data, p["offset"])
            if actual == p["original"]:
                status = "UNPATCHED"
            elif actual == p["patched"]:
                status = "PATCHED"
            else:
                status = f"UNKNOWN (0x{actual:08x})"
            print(f"  0x{p['offset']:08x}: {status} - {p['description']}")
        return

    output = args.output
    if not output:
        base, ext = os.path.splitext(args.input)
        output = f"{base}_patched{ext}"

    if args.input == output:
        backup = args.input + ".bak"
        shutil.copy2(args.input, backup)
        print(f"Backup: {backup}")

    if not patch_binary(args.input, output):
        sys.exit(1)


if __name__ == "__main__":
    main()
