#!/usr/bin/env python3
"""
Binary patch for libLogin.so - make Login.Check always return "OK"

Patch points (file offset == VMA for this binary):

  Patch 1 @ 0x628E4 : BEQ 0x62924  →  NOP
    - Skips the "login failed" return path; function falls through to "OK"
    - Before: 0E 00 00 0A
    - After : 00 00 A0 E1

  Patch 2 @ 0x62780 : BNE 0x627D8  →  B 0x62838
    - Makes HTTP response string comparison always take the success branch
    - Before: 14 00 00 1A
    - After : 2C 00 00 EA
"""

import shutil
import struct
import sys
from pathlib import Path

PATCHES = [
    # (file_offset, expected_bytes, replacement_bytes, description)
    (
        0x628E4,
        bytes([0x0E, 0x00, 0x00, 0x0A]),  # BEQ +0x3C (to failure path)
        bytes([0x00, 0x00, 0xA0, 0xE1]),  # NOP (MOV r0, r0)
        "BEQ→NOP: always fall through to OK return",
    ),
    (
        0x62780,
        bytes([0x14, 0x00, 0x00, 0x1A]),  # BNE +0x58 (skip success)
        bytes([0x2C, 0x00, 0x00, 0xEA]),  # B   +0xB8 (force success path)
        "BNE→B: response comparison always treated as match",
    ),
]


def patch(src: Path, dst: Path) -> None:
    shutil.copy2(src, dst)
    data = bytearray(dst.read_bytes())

    for offset, expected, replacement, desc in PATCHES:
        actual = bytes(data[offset : offset + 4])
        if actual != expected:
            print(f"[!] Offset 0x{offset:X}: expected {expected.hex()} got {actual.hex()} — skipping")
            continue
        data[offset : offset + 4] = replacement
        print(f"[+] Patched 0x{offset:X}: {desc}")

    dst.write_bytes(data)
    print(f"\n[*] Written → {dst}")


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "libLogin.so"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent / "libLogin_patched.so"

    if not src.exists():
        print(f"[-] Source not found: {src}")
        sys.exit(1)

    patch(src, dst)
