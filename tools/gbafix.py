#!/usr/bin/env python3
"""Write a GBA cartridge header title and complement checksum.
Does not embed the Nintendo logo (bytes 0x04..0x9F stay as the linker left them).
mGBA's built-in BIOS does not require the logo. If `gbafix` from devkitARM is on
PATH, the Makefile uses that instead, which does write the logo.
usage: gbafix.py rom.gba title"""
import sys

def fix(path, title):
    data = bytearray(open(path, 'rb').read())
    if len(data) < 0xC0:
        data.extend(b'\x00' * (0xC0 - len(data)))
    name = ''.join(ch for ch in title.upper() if 32 <= ord(ch) < 127)[:12]
    raw = name.encode('ascii')
    data[0xA0:0xAC] = raw + b'\x00' * (12 - len(raw))
    code = (raw + b'XXXX')[:4]
    data[0xAC:0xB0] = code
    data[0xB0:0xB2] = b'00'
    data[0xB2] = 0x96
    data[0xBC] = 0
    chk = 0
    for i in range(0xA0, 0xBD):
        chk = (chk - data[i]) & 0xFF
    data[0xBD] = (chk - 0x19) & 0xFF
    open(path, 'wb').write(data)
    # recompute to confirm
    chk = 0
    for i in range(0xA0, 0xBD):
        chk = (chk - data[i]) & 0xFF
    expect = (chk - 0x19) & 0xFF
    if data[0xBD] != expect or data[0xB2] != 0x96:
        raise SystemExit('header checksum failed')
    print('gbafix %s title=%r complement=0x%02X' % (path, name, data[0xBD]))

if __name__ == '__main__':
    fix(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'RETRO')
