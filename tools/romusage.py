#!/usr/bin/env python3
"""Print one ROM-usage line for the build log and the editor.

  romusage.py nes <file.nes> <file.map>
  romusage.py pc|uefi|gba <file>

NES numbers come from the ld65 map (the .nes file is padded to 32KB+8KB).
PRG is STARTUP+CODE+RODATA+ONCE+DATA. RAM is DATA+BSS inside the 768-byte
window at $0400. CHR is the CHARS segment. Mapper stays 0; overflow is an error.
"""
import os
import re
import sys

SEG = re.compile(r'^([A-Z][A-Z0-9_]*)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)')


def segments(path):
    found = {}
    for line in open(path):
        m = SEG.match(line)
        if m:
            found[m.group(1)] = int(m.group(4), 16)
    return found


def nes(rom, map_path):
    segs = segments(map_path)
    prg = (segs.get('STARTUP', 0) + segs.get('CODE', 0) + segs.get('RODATA', 0)
           + segs.get('ONCE', 0) + segs.get('DATA', 0))
    ram = segs.get('DATA', 0) + segs.get('BSS', 0)
    chars = segs.get('CHARS', 0)
    print('rom nes: PRG %d/32768 (%d%%) CHR %d/8192 RAM %d/768' % (
        prg, (prg * 100) // 32768 if prg else 0, chars, ram))
    if prg > 32768 or ram > 768:
        sys.exit('错误：NES NROM 的 32KB PRG 或 768 字节 RAM 放不下'
                 '（PRG %d，RAM %d）。这是 mapper 0，没有升级到 UxROM 或 MMC1。' % (prg, ram))


def blob(kind, path):
    n = os.path.getsize(path)
    print('rom %s: %d bytes' % (kind, n))


def main(argv):
    if len(argv) < 3:
        sys.exit('usage: romusage.py nes <rom> <map> | romusage.py pc|uefi|gba <file>')
    kind = argv[1]
    if kind == 'nes':
        if len(argv) != 4:
            sys.exit('usage: romusage.py nes <rom> <map>')
        nes(argv[2], argv[3])
    elif kind in ('pc', 'uefi', 'gba'):
        blob(kind, argv[2])
    else:
        sys.exit('unknown target %s' % kind)


if __name__ == '__main__':
    main(sys.argv)
