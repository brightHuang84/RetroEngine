#!/usr/bin/env python3
"""Pack games/<game>/maps into one C level table (tools/mappack.py games/<game>).

The editor stores plain tiles. This step compresses each column with RLE so a
long map stays small in ROM and a 6502 can decode a single column without a
RAM copy of the whole map.

Column packet (one column is always 30 tile bytes):
  0nnnnnnn  then n literal tile bytes          n = 1..127
  1nnnnnnn  then one tile, repeated n times    n = 2..127
index[c] is the u16 byte offset of column c. index[cols] is the blob length.
Attributes are the uncompressed 64-byte NES pages from map2c (first non-zero
palette in each 2x2). Collision flags are 256 bytes. The engine walks one
column's packets to answer tm_flags_at.

Height is 30 rows. Width is 1..512 columns. order.txt lists map names.
A leading "music <song>" line selects the song index from songs.txt.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import map2c
import ent2c

MAX_COLS = 512
ROWS = 30


def rle_encode(col):
    out = []
    i = 0
    n = len(col)
    while i < n:
        run = 1
        while i + run < n and col[i + run] == col[i] and run < 127:
            run += 1
        if run >= 2:
            out.append(0x80 | run)
            out.append(col[i])
            i += run
            continue
        start = i
        i += 1
        while i < n and (i - start) < 127:
            if i + 1 < n and col[i] == col[i + 1]:
                break
            i += 1
        count = i - start
        out.append(count)
        out.extend(col[start:i])
    return out


def rle_decode(blob, rows):
    out = []
    i = 0
    while len(out) < rows and i < len(blob):
        cmd = blob[i]
        i += 1
        n = cmd & 0x7F
        if cmd & 0x80:
            tile = blob[i]
            i += 1
            out.extend([tile] * n)
        else:
            out.extend(blob[i:i + n])
            i += n
    if len(out) < rows:
        raise ValueError('short column')
    return out[:rows]


def song_names(game_dir):
    path = os.path.join(game_dir, 'songs.txt')
    names = []
    if not os.path.exists(path):
        return names
    for line in open(path):
        parts = line.split('#', 1)[0].split()
        if len(parts) >= 2 and parts[0] == 'song':
            names.append(parts[1])
    return names


def music_of(text):
    for line in text.splitlines():
        parts = line.split('#', 1)[0].split()
        if len(parts) >= 2 and parts[0] == 'music':
            return parts[1]
    return ''


def read_order(game_dir):
    path = os.path.join(game_dir, 'maps', 'order.txt')
    if not os.path.exists(path):
        raise SystemExit('%s: 缺少 maps/order.txt' % game_dir)
    names = []
    for lineno, line in enumerate(open(path), 1):
        name = line.split('#', 1)[0].strip()
        if not name:
            continue
        if not (name[0].isalpha() and all(c.isalnum() or c == '_' for c in name)):
            raise SystemExit('%s:%d: 地图名 %s 需要是 C 标识符' % (path, lineno, name))
        if name in names:
            raise SystemExit('%s:%d: 地图 %s 重复' % (path, lineno, name))
        names.append(name)
    if not names:
        raise SystemExit('%s: 至少要有一张地图' % path)
    if len(names) > 255:
        raise SystemExit('%s: 最多 255 张地图' % path)
    return names


def columns_of(tiles):
    h = len(tiles)
    w = len(tiles[0])
    return [[tiles[y][x] for y in range(h)] for x in range(w)]


def c_bytes(name, data, per=24):
    lines = ['static const unsigned char %s[%d] = {' % (name, len(data))]
    for i in range(0, len(data), per):
        chunk = data[i:i + per]
        lines.append('  ' + ','.join(str(b) for b in chunk) + ',')
    lines.append('};')
    return lines


def c_index(name, index):
    lines = ['static const unsigned short %s[%d] = {' % (name, len(index))]
    for i in range(0, len(index), 16):
        chunk = index[i:i + 16]
        lines.append('  ' + ','.join(str(v) for v in chunk) + ',')
    lines.append('};')
    return lines


def pack_level(path, name, songs, spec):
    tiles, pal, solid, palmap = map2c.load(path)
    if not tiles:
        raise SystemExit('%s: 没有地图' % path)
    h = len(tiles)
    w = len(tiles[0])
    if any(len(r) != w for r in tiles):
        raise SystemExit('%s: 行的长度不一致' % path)
    if h != ROWS:
        raise SystemExit('%s: 高度必须是 %d 行（现在是 %d）。纵向不滚动。' % (path, ROWS, h))
    if not 1 <= w <= MAX_COLS:
        raise SystemExit('%s: 宽度必须是 1..%d 列（现在是 %d）。' % (path, MAX_COLS, w))
    cols = columns_of(tiles)
    blob = []
    index = [0]
    for col in cols:
        blob.extend(rle_encode(col))
        if len(blob) > 65535:
            raise SystemExit('%s: 压缩后超过 65535 字节，一条关卡的索引装不下。' % path)
        index.append(len(blob))
        if rle_decode(blob[index[-2]:index[-1]], h) != col:
            raise SystemExit('%s: 第 %d 列压缩后对不上' % (path, len(index) - 2))
    attrs = map2c.attribute_bytes(tiles, pal, palmap)
    flags = map2c.flag_bytes(solid)
    text = open(path).read()
    music_name = music_of(text)
    if not music_name:
        music_name = 'play' if 'play' in songs else (songs[0] if songs else '')
    if music_name:
        if music_name not in songs:
            raise SystemExit('%s: 没有曲子 %s。songs.txt 里有：%s' % (
                path, music_name, ', '.join(songs) or '（空）'))
        music = songs.index(music_name)
    else:
        music = 0
    ents = ent2c.entities_from_map_text(text, path)
    if spec.types:
        ent2c.check_count(ents, spec, path)
    sym = 'lv_%s' % name
    lines = ['/* %s: %d x %d, RLE %d bytes, music %s */' % (
        name, w, h, len(blob), music_name or str(music))]
    lines.extend(c_bytes(sym + '_pack', blob))
    lines.extend(c_index(sym + '_index', index))
    lines.extend(c_bytes(sym + '_attr', attrs))
    lines.extend(c_bytes(sym + '_flags', flags))
    if spec.types:
        lines.append(ent2c.emit_map(spec, ents, name, path).replace(
            'const unsigned char map_', 'static const unsigned char map_'))
    else:
        lines.append('#define MAP_%s_ENT_N 0' % name.upper())
        lines.append('static const unsigned char map_%s_ent[1] = {0};' % name)
    ent_n = len(ents) if spec.types else 0
    return {
        'name': name, 'lines': lines, 'sym': sym, 'cols': w, 'rows': h,
        'ent_n': ent_n, 'music': music, 'pack': len(blob),
    }


def emit(game_dir):
    names = read_order(game_dir)
    songs = song_names(game_dir)
    spec_path = os.path.join(game_dir, 'entities.txt')
    spec = ent2c.load_types(spec_path) if os.path.exists(spec_path) else ent2c.EntitySet()
    levels = []
    for name in names:
        path = os.path.join(game_dir, 'maps', name + '.txt')
        if not os.path.exists(path):
            raise SystemExit('找不到地图 %s' % path)
        levels.append(pack_level(path, name, songs, spec))
    out = [
        '/* GENERATED by tools/mappack.py — column RLE, do not edit. */',
        '#include "engine/engine.h"',
    ]
    if spec.types:
        out.append('#define ENT_LIMIT %d' % spec.limit)
        for t in spec.types:
            out.append('#define ENT_%s %d' % (t.name.upper(), t.id))
    for lv in levels:
        out.extend(lv['lines'])
    out.append('static const Level lv_table[%d] = {' % len(levels))
    for lv in levels:
        out.append(
            '  { %s_pack, %s_index, %s_attr, %s_flags, map_%s_ent, %d, %d, %d, %d },' % (
                lv['sym'], lv['sym'], lv['sym'], lv['sym'], lv['name'],
                lv['cols'], lv['rows'], lv['ent_n'], lv['music']))
    out.append('};')
    out.append('unsigned char game_level_count(void){ return %d; }' % len(levels))
    out.append('const Level *game_level(unsigned char n){')
    out.append('  if(n >= %d) n = 0;' % len(levels))
    out.append('  return &lv_table[n];')
    out.append('}')
    return '\n'.join(out) + '\n'


def main(game_dir):
    sys.stdout.write(emit(game_dir))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: mappack.py games/<game>')
    main(sys.argv[1])
