#!/usr/bin/env python3
"""Print one ROM-usage line for the build log and the editor.

  romusage.py nes <file.nes> <file.map>
  romusage.py pc|uefi|gba <file>

NES numbers come from the ld65 map. The .nes file is padded to the mapper's
PRG and CHR sizes. PRG used is real segment bytes (not the fill). RAM is
DATA+BSS inside the 768-byte window at $0400. CHR used is the CHARS segment.
WRAM used is the XRAM segment (the 8KB window the game actually placed there).
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


def header(path):
    b = open(path, 'rb').read(16)
    if b[:4] != b'NES\x1a':
        sys.exit('%s: not an iNES file' % path)
    nes2 = (b[7] & 0x0C) == 0x08
    mapper = (b[6] >> 4) | (b[7] & 0xF0)
    if nes2:
        mapper |= (b[8] & 0x0F) << 8
        prg_units = b[4] | ((b[9] & 0x0F) << 8)
        chr_units = b[5] | ((b[9] & 0xF0) << 4)
        shift = b[10] & 0x0F
        wram = (64 << shift) if shift else 0
    else:
        prg_units = b[4]
        chr_units = b[5]
        wram = 0
    return {
        'mapper': mapper,
        'nes2': nes2,
        'prg': prg_units * 16384,
        'chr': chr_units * 8192,
        'wram': wram,
    }


def nes(rom, map_path):
    info = header(rom)
    segs = segments(map_path)
    prg = (segs.get('STARTUP', 0) + segs.get('CODE', 0) + segs.get('RODATA', 0)
           + segs.get('ONCE', 0) + segs.get('DATA', 0) + segs.get('RESET', 0)
           + segs.get('VECTORS', 0))
    for i in range(16):
        prg += segs.get('BANK%d' % i, 0)
    ram = segs.get('DATA', 0) + segs.get('BSS', 0)
    chars = segs.get('CHARS', 0)
    wram_used = segs.get('XRAM', 0)
    prg_cap = info['prg'] or 32768
    chr_cap = info['chr'] or 8192
    line = 'rom nes: mapper %d PRG %d/%d (%d%%) CHR %d/%d RAM %d/768' % (
        info['mapper'], prg, prg_cap, (prg * 100) // prg_cap if prg else 0,
        chars, chr_cap, ram)
    if info['mapper'] == 5:
        line += ' WRAM %d/%d' % (wram_used, info['wram'] or 65536)
    print(line)
    if ram > 768:
        sys.exit('错误：NES 内部 RAM 只有 768 字节（用了 %d）。$0200 是 OAM，$0300 是 VRAM 队列，$0700 是 C 栈。' % ram)
    if info['mapper'] == 0 and (prg > 32768 or chars > 8192):
        sys.exit('错误：NES NROM 的 32KB PRG 放不下'
                 '（PRG %d，CHR %d）。这是 mapper 0。大的游戏用默认的 MMC5。' % (prg, chars))
    if info['mapper'] == 5 and (prg > prg_cap or chars > chr_cap):
        sys.exit('错误：MMC5 的 PRG 或 CHR 超出卡带容量（PRG %d/%d，CHR %d/%d）。' % (
            prg, prg_cap, chars, chr_cap))


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
