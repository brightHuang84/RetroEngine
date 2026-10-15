#!/usr/bin/env python3
"""Map -> C arrays: tiles, NES attribute bytes (64 per 32-wide page) and tile flags.
Input formats:
  * .txt  -- 'legend:' lines  "<char> <tile> [pal=N] [solid]" (';' starts a comment)  then 'map:' and rows of chars
  * .csv  -- Tiled CSV export (tile ids, Tiled gid-1), with optional sidecar <name>.legend
             lines "<tile> [pal=N] [solid]"
usage: map2c.py <map.txt|map.csv> <name>  >> out.c   (also writes declarations to stdout header block)"""
import sys, os, re
def parse_opts(tokens):
    pal = 0; solid = False
    for t in tokens:
        if t.startswith('pal='): pal = int(t[4:])
        if t == 'solid': solid = True
    return pal, solid
def load(path):
    tiles = []; pal = {}; solid = set(); palmap = None
    if path.endswith('.csv'):
        for line in open(path):
            line = line.strip().rstrip(',')
            if line: tiles.append([max(0, int(v) - 1) for v in line.split(',')])
        leg = os.path.splitext(path)[0] + '.legend'
        if os.path.exists(leg):
            for line in open(leg):
                p = line.split()
                if not p or p[0].startswith('#'): continue
                t = int(p[0], 0); pal[t], s = parse_opts(p[1:])
                if s: solid.add(t)
        return tiles, pal, solid, None
    legend = {}; mode = None
    for line in open(path):
        line = line.rstrip('\n')
        if line.strip() in ('legend:', 'map:', 'palmap:', 'entities:'): mode = line.strip(); continue
        if mode == 'legend:' and line.strip() and not line.startswith(';'):
            ch = line[0]; p = line[1:].split()
            t = int(p[0], 0); legend[ch] = t; pal[t], s = parse_opts(p[1:])
            if s: solid.add(t)
        elif mode == 'map:' and line:
            tiles.append([legend[c] for c in line])
        elif mode == 'palmap:' and line and not line.startswith(';'):
            if palmap is None: palmap = []
            palmap.append([int(c, 16) & 3 for c in line.strip()])
    if palmap is not None:
        if len(palmap) != len(tiles) or any(len(r) != len(tiles[0]) for r in palmap):
            raise SystemExit('%s: palmap size does not match the map' % path)
    return tiles, pal, solid, palmap
def main(path, name):
    tiles, pal, solid, palmap = load(path)
    h = len(tiles); w = len(tiles[0])
    assert all(len(r) == w for r in tiles), "ragged map"
    assert w <= 64 and h <= 30
    out = ['/* GENERATED from %s by tools/map2c.py */' % path,
           '#define MAP_%s_W %d' % (name.upper(), w), '#define MAP_%s_H %d' % (name.upper(), h)]
    out.append('const unsigned char map_%s[%d] = {' % (name, w * h))
    for r in tiles: out.append(','.join(str(t) for t in r) + ',')
    out.append('};')
    pages = (w + 31) // 32; at = []
    for pg in range(pages):
        for ay in range(8):
            for ax in range(8):
                b = 0
                for q, (dx, dy) in enumerate(((0, 0), (2, 0), (0, 2), (2, 2))):
                    x = pg * 32 + ax * 4 + dx; y = ay * 4 + dy
                    p = 0
                    if y < h and x < w:   # first non-zero palette in the 2x2 tile quadrant
                        for yy in (y, y + 1):
                            for xx in (x, x + 1):
                                if yy < h and xx < w:
                                    v = palmap[yy][xx] if palmap is not None else pal.get(tiles[yy][xx], 0)
                                    if v: p = p or v
                    b |= (p & 3) << (q * 2)
                at.append(b)
    out.append('const unsigned char map_%s_attr[%d] = {%s};' % (name, len(at), ','.join(str(v) for v in at)))
    fl = [1 if t in solid else 0 for t in range(256)]
    out.append('const unsigned char map_%s_flags[256] = {%s};' % (name, ','.join(str(v) for v in fl)))
    print('\n'.join(out))
if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
