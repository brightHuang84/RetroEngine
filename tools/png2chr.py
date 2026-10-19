#!/usr/bin/env python3
"""PNG tilesheet -> NES CHR + C array (single source of truth for graphics).

Sheet: 128 px wide. Each 128 px of height is one 256-tile (8KB) CHR page.
Height is a multiple of 8 and at most 16 pages (2048 px, 128KB).
Pixel color index = brightness level: black=0, dark grey=1, light grey=2, white=3
(nearest of 0/85/170/255). Indexed PNGs use palette index & 3 instead.

usage: png2chr.py tiles.png out.chr out.c [nrom|mmc5]
NROM writes one 8KB CHR file and rejects extra pages. MMC5 writes one 8KB
record per page (4KB tiles + 4KB pad); the linker fills the rest of the 128KB.
"""
import sys
from PIL import Image

PAGE_PX = 128
MAX_PAGES = 16


def main(src, chr_out, c_out, mapper='mmc5'):
    im = Image.open(src)
    if im.mode == 'P':
        px = lambda x, y: im.getpixel((x, y)) & 3
    else:
        g = im.convert('L')
        px = lambda x, y: min(3, (g.getpixel((x, y)) + 42) // 85)
    w, h = im.size
    if w != 128 or h <= 0 or h % 8 or h > PAGE_PX * MAX_PAGES:
        sys.exit('sheet must be 128 px wide, height a multiple of 8, at most %d' % (PAGE_PX * MAX_PAGES))
    pages = (h + PAGE_PX - 1) // PAGE_PX
    if mapper == 'nrom' and pages > 1:
        sys.exit('NROM 只有 8KB CHR（256 个图块）。tiles.png 有 %d 页。请用 MMC5，或把图块收进第一页。' % pages)
    tiles = bytearray(pages * 4096)
    for t in range((h // 8) * 16):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        for r in range(8):
            lo = hi = 0
            for c in range(8):
                v = px(tx + c, ty + r)
                lo |= (v & 1) << (7 - c)
                hi |= (v >> 1) << (7 - c)
            tiles[t * 16 + r] = lo
            tiles[t * 16 + 8 + r] = hi
    chr_file = bytearray()
    for p in range(pages):
        chr_file += tiles[p * 4096:(p + 1) * 4096]
        chr_file += bytes(4096)
    open(chr_out, 'wb').write(chr_file)
    with open(c_out, 'w') as f:
        f.write('/* GENERATED from %s by tools/png2chr.py — %d CHR page(s) */\n' % (src, pages))
        f.write('const unsigned char chr_tiles[%d] = {\n' % len(tiles))
        for i in range(0, len(tiles), 16):
            f.write(','.join('%d' % b for b in tiles[i:i + 16]) + ',\n')
        f.write('};\n')


if __name__ == '__main__':
    if len(sys.argv) not in (4, 5):
        sys.exit('usage: png2chr.py tiles.png out.chr out.c [nrom|mmc5]')
    main(*sys.argv[1:5]) if len(sys.argv) == 5 else main(*sys.argv[1:4])
