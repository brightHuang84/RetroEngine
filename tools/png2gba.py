#!/usr/bin/env python3
"""PNG tilesheet -> GBA 4bpp tiles (same pixels as tools/png2chr.py).
Sheet: 128 px wide, up to 128 px tall. Pixel index 0..3, low nibble = left pixel.
256 tiles * 32 bytes = 8192. usage: png2gba.py tiles.png out.c"""
import sys
from PIL import Image

def main(src, c_out):
    im = Image.open(src)
    if im.mode == 'P':
        px = lambda x, y: im.getpixel((x, y)) & 3
    else:
        g = im.convert('L')
        px = lambda x, y: min(3, (g.getpixel((x, y)) + 42) // 85)
    w, h = im.size
    assert w == 128 and h <= 128 and h % 8 == 0, "sheet must be 128 px wide, <=128 tall"
    data = bytearray(8192)
    for t in range((h // 8) * 16):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        base = t * 32
        for r in range(8):
            for c in range(0, 8, 2):
                v0 = px(tx + c, ty + r)
                v1 = px(tx + c + 1, ty + r)
                data[base + r * 4 + c // 2] = (v0 & 3) | ((v1 & 3) << 4)
    with open(c_out, 'w') as f:
        f.write('/* GENERATED from %s by tools/png2gba.py */\n' % src)
        f.write('const unsigned char gba_tiles[8192] = {\n')
        for i in range(0, 8192, 16):
            f.write(','.join('%d' % b for b in data[i:i + 16]) + ',\n')
        f.write('};\n')

if __name__ == '__main__':
    main(*sys.argv[1:3])
