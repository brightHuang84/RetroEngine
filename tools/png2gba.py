#!/usr/bin/env python3
"""PNG tilesheet -> GBA 4bpp tiles (same pixels as tools/png2chr.py).

Sheet: 128 px wide, up to 16 pages of 128 px (256 tiles each).
Pixel index 0..3, low nibble = left pixel. One page is 8192 bytes.
usage: png2gba.py tiles.png out.c"""
import sys
from PIL import Image

PAGE_PX = 128
MAX_PAGES = 16


def main(src, c_out):
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
    data = bytearray(pages * 8192)
    for t in range((h // 8) * 16):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        base = t * 32
        for r in range(8):
            for c in range(0, 8, 2):
                v0 = px(tx + c, ty + r)
                v1 = px(tx + c + 1, ty + r)
                data[base + r * 4 + c // 2] = (v0 & 3) | ((v1 & 3) << 4)
    with open(c_out, 'w') as f:
        f.write('/* GENERATED from %s by tools/png2gba.py — %d page(s) */\n' % (src, pages))
        f.write('const unsigned char gba_tiles[%d] = {\n' % len(data))
        for i in range(0, len(data), 16):
            f.write(','.join('%d' % b for b in data[i:i + 16]) + ',\n')
        f.write('};\n')


if __name__ == '__main__':
    main(*sys.argv[1:3])
