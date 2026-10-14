#!/usr/bin/env python3
"""PNG tilesheet -> NES CHR + C array (single source of truth for graphics).
Sheet: 128 px wide, up to 128 px tall (16x16 tiles of 8x8 = tiles 0..255, row-major).
Pixel color index = brightness level: black=0, dark grey=1, light grey=2, white=3
(nearest of 0/85/170/255). Indexed PNGs use palette index & 3 instead.
usage: png2chr.py tiles.png out.chr out.c"""
import sys
from PIL import Image
def main(src, chr_out, c_out):
    im = Image.open(src)
    if im.mode == 'P':
        px = lambda x, y: im.getpixel((x, y)) & 3
    else:
        g = im.convert('L')
        px = lambda x, y: min(3, (g.getpixel((x, y)) + 42) // 85)
    w, h = im.size
    assert w == 128 and h <= 128 and h % 8 == 0, "sheet must be 128 px wide, <=128 tall"
    data = bytearray(4096)
    for t in range((h // 8) * 16):
        tx, ty = (t % 16) * 8, (t // 16) * 8
        for r in range(8):
            lo = hi = 0
            for c in range(8):
                v = px(tx + c, ty + r)
                lo |= (v & 1) << (7 - c); hi |= (v >> 1) << (7 - c)
            data[t * 16 + r] = lo; data[t * 16 + 8 + r] = hi
    open(chr_out, 'wb').write(bytes(data) + bytes(4096))
    with open(c_out, 'w') as f:
        f.write('/* GENERATED from %s by tools/png2chr.py */\n' % src)
        f.write('const unsigned char chr_tiles[4096] = {\n')
        for i in range(0, 4096, 16): f.write(','.join('%d' % b for b in data[i:i+16]) + ',\n')
        f.write('};\n')
if __name__ == '__main__': main(*sys.argv[1:4])
