"""Load and save a RetroEngine game folder. No Qt.

tiles.png is a 128px-wide sheet of 8x8 tiles, four grey levels.
palette.txt is 32 NES color indices (8 groups of 4).
Maps are the text format read by tools/map2c.py, with an optional palmap.
Songs are songs.txt, the format read by tools/txt2mus.py.
"""
import os
import sys

from PIL import Image

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import txt2mus
import ent2c

GREY = (0, 85, 170, 255)
# Same table as render/render_soft.c. Index is the NES color 0..63.
NES_RGB = [
    0x545454, 0x001E74, 0x081090, 0x300088, 0x440064, 0x5C0030, 0x540400, 0x3C1800,
    0x202A00, 0x083A00, 0x004000, 0x003C00, 0x00323C, 0x000000, 0x000000, 0x000000,
    0x989698, 0x084CC4, 0x3032EC, 0x5C1EE4, 0x8814B0, 0xA01464, 0x982220, 0x783C00,
    0x545A00, 0x287200, 0x087C00, 0x007628, 0x006678, 0x000000, 0x000000, 0x000000,
    0xECEEEC, 0x4C9AEC, 0x787CEC, 0xB062EC, 0xE454EC, 0xEC58B4, 0xEC6A64, 0xD48820,
    0xA0AA00, 0x74C400, 0x4CD020, 0x38CC6C, 0x38B4CC, 0x3C3C3C, 0x000000, 0x000000,
    0xECEEEC, 0xA8CCEC, 0xBCBCEC, 0xD4B2EC, 0xECAEEC, 0xECAED4, 0xECB4B0, 0xE4C490,
    0xCCD278, 0xB4DE78, 0xA8E290, 0x98E2B4, 0xA0D6E4, 0xA0A2A0, 0x000000, 0x000000,
]
PAL_NAMES = ['背景 0', '背景 1', '背景 2', '背景 3', '精灵 0', '精灵 1', '精灵 2', '精灵 3']
CHAN_NAMES = ['pulse1', 'pulse2', 'triangle', 'noise']
CHAN_LABELS = ['方波 1', '方波 2', '三角波', '噪声']
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
CHAR_POOL = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@%&?~'


def rgb_of(nes_index):
    return NES_RGB[nes_index & 63]


def load_palette(path):
    vals = []
    for line in open(path):
        line = line.split('#', 1)[0]
        for tok in line.split():
            vals.append(int(tok, 16) & 63)
    if len(vals) != 32:
        raise ValueError('%s: expected 32 colors, got %d' % (path, len(vals)))
    return vals


def save_palette(path, vals):
    lines = [
        '# NES palette. Eight rows of four indices (00-3F):',
        '# BG0 BG1 BG2 BG3, then sprite 0..3.',
        '# Background color 0 uses only the first entry of BG0 (the shared backdrop).',
    ]
    for i in range(0, 32, 4):
        lines.append(' '.join('%02X' % (v & 63) for v in vals[i:i + 4]))
    open(path, 'w').write('\n'.join(lines) + '\n')


class Tiles(object):
    def __init__(self, pixels, width, height):
        self.pixels = bytearray(pixels)  # row-major, values 0..3
        self.w = width
        self.h = height

    def copy(self):
        return Tiles(self.pixels, self.w, self.h)

    def get(self, x, y):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return 0
        return self.pixels[y * self.w + x]

    def set(self, x, y, value):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.pixels[y * self.w + x] = value & 3

    def tile_origin(self, index):
        return (index % 16) * 8, (index // 16) * 8

    def tile_get(self, index, x, y):
        ox, oy = self.tile_origin(index)
        return self.get(ox + x, oy + y)

    def tile_set(self, index, x, y, value):
        ox, oy = self.tile_origin(index)
        self.set(ox + x, oy + y, value)

    def tile_grid(self, index):
        ox, oy = self.tile_origin(index)
        return [self.get(ox + x, oy + y) for y in range(8) for x in range(8)]

    def tile_paste(self, index, grid):
        ox, oy = self.tile_origin(index)
        for i, v in enumerate(grid):
            self.set(ox + (i % 8), oy + (i // 8), v)

    def count(self):
        return (self.h // 8) * 16


def load_tiles(path):
    im = Image.open(path)
    w, h = im.size
    if w != 128 or h > 128 or h % 8:
        raise ValueError('%s: sheet must be 128 px wide and a multiple of 8 tall' % path)
    pixels = bytearray(w * h)
    indexed = im.mode == 'P'
    grey = None if indexed else im.convert('L')
    for y in range(h):
        for x in range(w):
            if indexed:
                v = im.getpixel((x, y)) & 3
            else:
                v = min(3, (grey.getpixel((x, y)) + 42) // 85)
            pixels[y * w + x] = v
    return Tiles(pixels, w, h)


def save_tiles(path, tiles):
    im = Image.new('L', (tiles.w, tiles.h))
    im.putdata([GREY[v & 3] for v in tiles.pixels])
    im.save(path)


class LegendEntry(object):
    def __init__(self, char, tile, pal, solid):
        self.char = char
        self.tile = tile & 255
        self.pal = pal & 3
        self.solid = bool(solid)


class GameMap(object):
    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.legend = []
        self.rows = []
        self.override = None  # None, or h rows of w ints/None
        self.entities = []
        self.music = ''
        self.original = ''

    def copy_state(self):
        ov = None
        if self.override is not None:
            ov = [row[:] for row in self.override]
        legs = [(e.char, e.tile, e.pal, e.solid) for e in self.legend]
        return (tuple(self.rows), tuple(legs), ov, tuple(e.copy() for e in self.entities), self.music)

    def restore_state(self, state):
        rows, legs, ov, ents = state[:4]
        self.rows = list(rows)
        self.legend = [LegendEntry(c, t, p, s) for c, t, p, s in legs]
        self.override = [row[:] for row in ov] if ov is not None else None
        self.entities = [e.copy() for e in ents]
        if len(state) > 4:
            self.music = state[4]

    @property
    def w(self):
        return len(self.rows[0]) if self.rows else 0

    @property
    def h(self):
        return len(self.rows)

    def _by_char(self):
        return {e.char: e for e in self.legend}

    def tile_at(self, x, y):
        ent = self._by_char().get(self.rows[y][x])
        return ent.tile if ent else 0

    def legend_pal(self, x, y):
        ent = self._by_char().get(self.rows[y][x])
        return ent.pal if ent else 0

    def effective_pal(self, x, y):
        if self.override is not None and self.override[y][x] is not None:
            return self.override[y][x]
        return self.legend_pal(x, y)

    def solid_of(self, tile):
        for e in self.legend:
            if e.tile == tile:
                return e.solid
        return False

    def set_solid(self, tile, solid):
        found = False
        for e in self.legend:
            if e.tile == tile:
                e.solid = bool(solid)
                found = True
        return found

    def _ensure_override(self):
        if self.override is None:
            self.override = [[None] * self.w for _ in range(self.h)]

    def _clear_override(self, x, y):
        if self.override is not None:
            self.override[y][x] = None

    def has_override(self):
        if self.override is None:
            return False
        return any(v is not None for row in self.override for v in row)

    def _unused_char(self):
        used = set(e.char for e in self.legend)
        for ch in CHAR_POOL:
            if ch not in used:
                return ch
        raise ValueError('no free legend character')

    def _find(self, tile, pal, solid):
        for e in self.legend:
            if e.tile == tile and e.pal == pal and e.solid == solid:
                return e
        return None

    def _find_tile(self, tile):
        for e in self.legend:
            if e.tile == tile:
                return e
        return None

    def _set_char(self, x, y, char):
        row = self.rows[y]
        self.rows[y] = row[:x] + char + row[x + 1:]

    def place(self, x, y, tile, pal):
        """Put tile at (x, y) and record palette pal. Same tile id keeps one legend palette;
        a different palette is stored as a per-cell override."""
        tile &= 255
        pal &= 3
        solid = self.solid_of(tile)
        ent = self._find(tile, pal, solid)
        if ent is None:
            same = self._find_tile(tile)
            if same is None:
                ent = LegendEntry(self._unused_char(), tile, pal, solid)
                self.legend.append(ent)
                self._set_char(x, y, ent.char)
                self._clear_override(x, y)
                return
            self._set_char(x, y, same.char)
            if pal != same.pal:
                self._ensure_override()
                self.override[y][x] = pal
            else:
                self._clear_override(x, y)
            return
        self._set_char(x, y, ent.char)
        self._clear_override(x, y)

    def paint(self, x, y, tile, pal, auto_block):
        if auto_block:
            x0, y0 = x & ~1, y & ~1
            for dy in (0, 1):
                for dx in (0, 1):
                    cx, cy = x0 + dx, y0 + dy
                    if cx >= self.w or cy >= self.h:
                        continue
                    if cx == x and cy == y:
                        self.place(cx, cy, tile, pal)
                    else:
                        self.place(cx, cy, self.tile_at(cx, cy), pal)
        else:
            self.place(x, y, tile, pal)

    def emit(self, spec=None):
        lines = []
        if self.music:
            lines.append('music %s' % self.music)
        lines.append('legend:')
        for e in self.legend:
            line = '%s 0x%02X pal=%d' % (e.char, e.tile, e.pal)
            if e.solid:
                line += ' solid'
            lines.append(line)
        lines.append('map:')
        lines.extend(self.rows)
        if self.has_override():
            lines.append('palmap:')
            for y in range(self.h):
                lines.append(''.join(str(self.effective_pal(x, y)) for x in range(self.w)))
        text = '\n'.join(lines) + '\n'
        extra = ent2c.format_entities(self.entities, spec)
        if extra:
            text += extra
        return text


def load_map(path):
    name = os.path.splitext(os.path.basename(path))[0]
    gm = GameMap(name, path)
    gm.original = open(path).read()
    mode = None
    legend = {}
    for line in gm.original.splitlines():
        raw = line.rstrip('\n')
        stripped = raw.strip()
        if mode is None and stripped.startswith('music ') and not stripped.startswith('music:'):
            parts = stripped.split()
            if len(parts) >= 2:
                gm.music = parts[1]
            continue
        if raw.strip() in ('legend:', 'map:', 'palmap:', 'entities:'):
            mode = raw.strip()
            continue
        if mode == 'legend:' and raw.strip() and not raw.startswith(';'):
            ch = raw[0]
            parts = raw[1:].split()
            tile = int(parts[0], 0)
            pal, solid = 0, False
            for tok in parts[1:]:
                if tok.startswith('pal='):
                    pal = int(tok[4:]) & 3
                elif tok == 'solid':
                    solid = True
            gm.legend.append(LegendEntry(ch, tile, pal, solid))
            legend[ch] = tile
        elif mode == 'map:' and raw:
            gm.rows.append(raw)
        elif mode == 'palmap:' and raw and not raw.startswith(';'):
            if gm.override is None:
                gm.override = []
            gm.override.append([int(c, 16) & 3 for c in raw.strip()])
    if not gm.rows:
        raise ValueError('%s: no map rows' % path)
    w = len(gm.rows[0])
    if any(len(r) != w for r in gm.rows):
        raise ValueError('%s: ragged map' % path)
    for y, row in enumerate(gm.rows):
        for ch in row:
            if ch not in legend:
                raise ValueError('%s: character %r is not in the legend' % (path, ch))
    gm.entities = ent2c.entities_from_map_text(gm.original, path)
    return gm


def maps_dir(game_dir):
    return os.path.join(game_dir, 'maps')


def order_path(game_dir):
    return os.path.join(game_dir, 'maps', 'order.txt')


def order_text(names):
    return '# 关卡顺序，一行一个名字。\n' + '\n'.join(names) + '\n'


def valid_map_name(name):
    return bool(name) and name[0].isalpha() and all(c.isalnum() or c == '_' for c in name)


def list_maps(game_dir):
    op = order_path(game_dir)
    if os.path.exists(op):
        out = []
        for line in open(op):
            name = line.split('#', 1)[0].strip()
            if not name:
                continue
            out.append(load_map(os.path.join(maps_dir(game_dir), name + '.txt')))
        return out
    out = []
    if not os.path.isdir(game_dir):
        return out
    for fn in sorted(os.listdir(game_dir)):
        if not fn.endswith('.txt'):
            continue
        if fn.lower() in ('songs.txt', 'palette.txt', 'entities.txt'):
            continue
        path = os.path.join(game_dir, fn)
        text = open(path).read()
        if '\nmap:' in '\n' + text or text.startswith('map:'):
            out.append(load_map(path))
    return out


def attribute_bytes(w, h, pal_at):
    """NES attribute bytes, matching tools/map2c.py. pal_at(x, y) -> 0..3."""
    pages = (w + 31) // 32
    at = []
    for pg in range(pages):
        for ay in range(8):
            for ax in range(8):
                b = 0
                for q, (dx, dy) in enumerate(((0, 0), (2, 0), (0, 2), (2, 2))):
                    x = pg * 32 + ax * 4 + dx
                    y = ay * 4 + dy
                    p = 0
                    if y < h and x < w:
                        for yy in (y, y + 1):
                            for xx in (x, x + 1):
                                if 0 <= yy < h and 0 <= xx < w:
                                    v = pal_at(xx, yy) & 3
                                    if v:
                                        p = p or v
                    b |= (p & 3) << (q * 2)
                at.append(b)
    return at


def resolved_palette(tx, ty, attrs):
    pg = tx >> 5
    lx = tx & 31
    idx = pg * 64 + (ty >> 2) * 8 + (lx >> 2)
    if idx < 0 or idx >= len(attrs):
        return 0
    shift = (4 if (ty & 2) else 0) + (2 if (lx & 2) else 0)
    return (attrs[idx] >> shift) & 3


def attribute_conflicts(w, h, pal_at):
    """2x2 blocks that contain two different non-zero palettes."""
    found = []
    pages = (w + 31) // 32
    for pg in range(pages):
        for ay in range(8):
            for ax in range(8):
                for dx, dy in ((0, 0), (2, 0), (0, 2), (2, 2)):
                    x = pg * 32 + ax * 4 + dx
                    y = ay * 4 + dy
                    pals = set()
                    if y < h and x < w:
                        for yy in (y, y + 1):
                            for xx in (x, x + 1):
                                if 0 <= yy < h and 0 <= xx < w:
                                    v = pal_at(xx, yy) & 3
                                    if v:
                                        pals.add(v)
                    if len(pals) > 1:
                        found.append((x, y, tuple(sorted(pals))))
    return found


class Channel(object):
    def __init__(self):
        self.duty = 2
        self.vol = 10
        self.once = False
        self.events = []   # (note token, duration token)
        self.loop_at = None


class Song(object):
    def __init__(self, name):
        self.name = name
        self.tempo = 120
        self.ch = [None, None, None, None]

    def clone(self):
        s = Song(self.name)
        s.tempo = self.tempo
        for i, ch in enumerate(self.ch):
            if ch is None:
                continue
            c = Channel()
            c.duty, c.vol, c.once = ch.duty, ch.vol, ch.once
            c.events = list(ch.events)
            c.loop_at = ch.loop_at
            s.ch[i] = c
        return s


def _strip_comment(line):
    out = []
    i = 0
    while i < len(line):
        if line[i] == '#' and (i == 0 or line[i - 1].isspace()):
            break
        out.append(line[i])
        i += 1
    return ''.join(out).strip()


def parse_songs(text):
    songs = []
    cur = None
    chan = None
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line or line.startswith(';'):
            continue
        parts = line.split()
        key = parts[0].lower()
        if key == 'song':
            cur = Song(parts[1])
            songs.append(cur)
            chan = None
            continue
        if cur is None:
            continue
        if key == 'tempo':
            cur.tempo = int(parts[1])
            continue
        if key in txt2mus.CHANS:
            chan = Channel()
            cur.ch[txt2mus.CHANS[key]] = chan
            i = 1
            while i < len(parts):
                k = parts[i].lower()
                if k == 'once':
                    chan.once = True
                    i += 1
                    continue
                if k == 'duty':
                    chan.duty = int(parts[i + 1])
                elif k == 'vol':
                    chan.vol = int(parts[i + 1])
                elif k == 'mode':
                    chan.duty = int(parts[i + 1])
                i += 2
            continue
        if key == 'loop':
            if chan is not None:
                chan.loop_at = len(chan.events)
            continue
        if chan is None or len(parts) % 2:
            continue
        for n in range(0, len(parts), 2):
            chan.events.append((parts[n], parts[n + 1]))
    return songs


def emit_songs(songs):
    lines = []
    for song in songs:
        lines.append('song %s' % song.name)
        lines.append('tempo %d' % song.tempo)
        lines.append('')
        for ci, ch in enumerate(song.ch):
            if ch is None or not ch.events:
                continue
            if ci == 3:
                # Omitting mode keeps txt2mus's default duty 2, which is the
                # same noise mode (bit 0 clear) as the example songs.
                head = 'noise vol %d' % ch.vol
                if (ch.duty & 1) or ch.duty == 0:
                    head += ' mode %d' % (ch.duty & 1)
            elif ci == 2:
                head = 'triangle vol %d' % ch.vol
            else:
                head = '%s duty %d vol %d' % (CHAN_NAMES[ci], ch.duty & 3, ch.vol)
            if ch.once:
                head += ' once'
            lines.append(head)
            wrote_loop = False
            bits = []

            def flush():
                for i in range(0, len(bits), 8):
                    lines.append('  ' + ' '.join(bits[i:i + 8]))
                del bits[:]

            for i, (note, dur) in enumerate(ch.events):
                if ch.loop_at not in (None, 0) and i == ch.loop_at:
                    flush()
                    lines.append('  loop')
                    wrote_loop = True
                bits.append('%s %s' % (note, dur))
            flush()
            if ch.loop_at not in (None, 0) and not wrote_loop:
                lines.append('  loop')
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def song_frames(song):
    """Per-channel list of (pitch index, frames), using txt2mus so playback matches the build."""
    import tempfile
    text = emit_songs([song])
    fd, path = tempfile.mkstemp(suffix='.txt')
    os.close(fd)
    try:
        open(path, 'w').write(text)
        parsed = txt2mus.parse(path)
    finally:
        os.remove(path)
    return parsed[0]


class Project(object):
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.name = os.path.basename(self.root)
        self.palette_path = os.path.join(self.root, 'palette.txt')
        self.tiles_path = os.path.join(self.root, 'tiles.png')
        self.songs_path = os.path.join(self.root, 'songs.txt')
        self.code_path = os.path.join(self.root, 'game.c')
        self.palette = load_palette(self.palette_path)
        self.tiles = load_tiles(self.tiles_path)
        self.maps = list_maps(self.root)
        self.songs_text = open(self.songs_path).read() if os.path.exists(self.songs_path) else ''
        self.songs = parse_songs(self.songs_text) if self.songs_text else []
        self.code = open(self.code_path).read() if os.path.exists(self.code_path) else ''
        self.entities_path = os.path.join(self.root, 'entities.txt')
        self.entity_spec = ent2c.load_types(self.entities_path)
        self.removed_maps = []
        self.dirty = {
            'palette': False, 'tiles': False, 'maps': False,
            'songs': False, 'code': False, 'entities': False,
        }

    def map_by_name(self, name):
        for m in self.maps:
            if m.name == name:
                return m
        return self.maps[0] if self.maps else None

    def _fresh_map(self, name, width, src):
        if not valid_map_name(name):
            raise ValueError('地图名要是字母开头的英文名')
        if any(m.name == name for m in self.maps):
            raise ValueError('已经有地图 %s' % name)
        if width % 32 or not 32 <= width <= 512:
            raise ValueError('宽度要是 32 的倍数，32 到 512')
        gm = GameMap(name, os.path.join(maps_dir(self.root), name + '.txt'))
        if src is None:
            gm.legend = [LegendEntry('.', 0x20, 0, False)]
            gm.music = 'play'
        else:
            gm.legend = [LegendEntry(e.char, e.tile, e.pal, e.solid) for e in src.legend]
            gm.music = src.music
        fill = gm.legend[0].char if gm.legend else '.'
        gm.rows = [fill * width for _ in range(30)]
        return gm

    def add_map(self, name, width, src=None):
        gm = self._fresh_map(name, width, src)
        self.maps.append(gm)
        self.dirty['maps'] = True
        return gm

    def duplicate_map(self, name):
        src = self.map_by_name(name)
        if src is None:
            raise ValueError('没有这张地图')
        new_name = name + '_copy'
        n = 2
        while any(m.name == new_name for m in self.maps):
            new_name = '%s_copy%d' % (name, n)
            n += 1
        gm = self._fresh_map(new_name, src.w if src.w % 32 == 0 else 32, None)
        gm.legend = [LegendEntry(e.char, e.tile, e.pal, e.solid) for e in src.legend]
        gm.rows = list(src.rows)
        gm.override = [row[:] for row in src.override] if src.override is not None else None
        gm.entities = [e.copy() for e in src.entities]
        gm.music = src.music
        idx = self.maps.index(src) + 1
        self.maps.insert(idx, gm)
        self.dirty['maps'] = True
        return gm

    def rename_map(self, old, new):
        if not valid_map_name(new):
            raise ValueError('地图名要是字母开头的英文名')
        src = self.map_by_name(old)
        if src is None:
            raise ValueError('没有这张地图')
        if new != old and any(m.name == new for m in self.maps):
            raise ValueError('已经有地图 %s' % new)
        if os.path.isfile(src.path):
            self.removed_maps.append(src.path)
        src.name = new
        src.path = os.path.join(maps_dir(self.root), new + '.txt')
        src.original = ''
        self.dirty['maps'] = True
        return src

    def delete_map(self, name):
        if len(self.maps) <= 1:
            raise ValueError('至少留一张地图')
        src = self.map_by_name(name)
        if src is None:
            raise ValueError('没有这张地图')
        if os.path.isfile(src.path):
            self.removed_maps.append(src.path)
        self.maps.remove(src)
        self.dirty['maps'] = True

    def move_map(self, name, delta):
        src = self.map_by_name(name)
        if src is None:
            return
        i = self.maps.index(src)
        j = i + delta
        if j < 0 or j >= len(self.maps):
            return
        self.maps[i], self.maps[j] = self.maps[j], self.maps[i]
        self.dirty['maps'] = True

    def save(self):
        if self.dirty['palette']:
            save_palette(self.palette_path, self.palette)
            self.dirty['palette'] = False
        if self.dirty['tiles']:
            save_tiles(self.tiles_path, self.tiles)
            self.dirty['tiles'] = False
        if self.dirty['entities']:
            ent2c.save_types(self.entities_path, self.entity_spec)
            self.dirty['entities'] = False
        if self.dirty['maps']:
            directory = maps_dir(self.root)
            os.makedirs(directory, exist_ok=True)
            for m in self.maps:
                text = m.emit(self.entity_spec)
                m.path = os.path.join(directory, m.name + '.txt')
                if text != m.original or not os.path.exists(m.path):
                    open(m.path, 'w').write(text)
                    m.original = text
            op = order_path(self.root)
            text = order_text([m.name for m in self.maps])
            old = open(op).read() if os.path.exists(op) else None
            if old != text:
                open(op, 'w').write(text)
            for path in self.removed_maps:
                if os.path.isfile(path) and path not in [m.path for m in self.maps]:
                    os.remove(path)
            self.removed_maps = []
            self.dirty['maps'] = False
        if self.dirty['songs']:
            self.songs_text = emit_songs(self.songs)
            open(self.songs_path, 'w').write(self.songs_text)
            self.dirty['songs'] = False
        if self.dirty['code']:
            open(self.code_path, 'w').write(self.code)
            self.dirty['code'] = False

    def any_dirty(self):
        return any(self.dirty.values())


BLANK_GAME_C = r'''/* 空白游戏。只包含 engine.h，不要写平台相关代码。 */
#include "../../engine/engine.h"
#include "assets.h"
#include "music.h"

static void init(void){
  gfx_palette(game_palette);
  level_load(0);
  bg_text(10, 14, "NEW GAME");
  music_play(MUS_TITLE);
}
static void update(void){}
static void draw(void){}
const Scene scene = { init, update, draw };
const Scene *game_boot(void){ return &scene; }
u8 game_autopilot(void){ return 0; }
'''

BLANK_SONG = '''song title
tempo 120

pulse1 duty 2 vol 10
  C4 8 E4 8 G4 8 C5 8
  G4 4 R 4

triangle vol 12
  C3 4 G2 4
  C3 2
'''

BLANK_PALETTE = [
    0x0F, 0x16, 0x26, 0x06, 0x0F, 0x27, 0x37, 0x17,
    0x0F, 0x2A, 0x3A, 0x1A, 0x0F, 0x10, 0x00, 0x30,
    0x0F, 0x30, 0x30, 0x10, 0x0F, 0x21, 0x31, 0x11,
    0x0F, 0x30, 0x30, 0x30, 0x0F, 0x30, 0x30, 0x30,
]


def create_project(games_dir, name, template_root):
    """template_root is an existing game directory, or None for a blank game.
    A blank game copies tiles.png from breakout when that sheet exists, so
    ASCII text still has glyphs."""
    import shutil
    dst = os.path.join(games_dir, name)
    if os.path.exists(dst):
        raise ValueError('游戏 %s 已经存在' % name)
    if template_root:
        shutil.copytree(template_root, dst)
        return dst
    os.makedirs(dst)
    src_tiles = os.path.join(games_dir, 'breakout', 'tiles.png')
    if os.path.exists(src_tiles):
        shutil.copy(src_tiles, os.path.join(dst, 'tiles.png'))
    else:
        im = Image.new('L', (128, 128), 0)
        im.save(os.path.join(dst, 'tiles.png'))
    save_palette(os.path.join(dst, 'palette.txt'), BLANK_PALETTE)
    os.makedirs(os.path.join(dst, 'maps'))
    rows = ['.' * 32 for _ in range(30)]
    legend = 'music title\nlegend:\n. 0x20 pal=0\n# 0x82 pal=3 solid\nmap:\n' + '\n'.join(rows) + '\n'
    open(os.path.join(dst, 'maps', 'level.txt'), 'w').write(legend)
    open(os.path.join(dst, 'maps', 'order.txt'), 'w').write(order_text(['level']))
    open(os.path.join(dst, 'songs.txt'), 'w').write(BLANK_SONG)
    open(os.path.join(dst, 'game.c'), 'w').write(BLANK_GAME_C)
    return dst
