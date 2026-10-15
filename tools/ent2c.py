#!/usr/bin/env python3
"""Entity types and per-map placements -> packed C tables.

games/<game>/entities.txt defines types. Each map may end with an
'entities:' section. One instance is 12 bytes:

  type, x_lo, x_hi, y, prop0_lo, prop0_hi, prop1_lo, prop1_hi,
  prop2_lo, prop2_hi, prop3_lo, prop3_hi

At most 4 named u16 properties, and at most `limit` instances on a map
(never more than 32). cc65 reads them with the ent_* macros in engine.h.
usage: ent2c.py games/<game>     prints C for every map, or nothing if
                                 entities.txt is absent
"""
import os
import sys

ENT_BYTES = 12
ENT_ABS_MAX = 32
MAX_PROPS = 4


class EntityType(object):
    def __init__(self, name, ident, w, h, pal):
        self.name = name
        self.id = ident
        self.w = w
        self.h = h
        self.pal = pal
        self.label = ''
        self.sprites = []   # (dx, dy, tile)
        self.props = []     # (name, default)


class Entity(object):
    def __init__(self, type_name, x, y, props=None):
        self.type = type_name
        self.x = int(x)
        self.y = int(y)
        self.props = dict(props or {})

    def copy(self):
        return Entity(self.type, self.x, self.y, self.props)


class EntitySet(object):
    def __init__(self):
        self.limit = ENT_ABS_MAX
        self.types = []

    def by_name(self, name):
        for t in self.types:
            if t.name == name:
                return t
        return None


def _tokens(line):
    line = line.split('#', 1)[0].strip()
    if not line or line.startswith(';'):
        return []
    return line.split()


def load_types(path):
    spec = EntitySet()
    if not os.path.exists(path):
        return spec
    cur = None
    seen = set()
    ids = set()
    for lineno, raw in enumerate(open(path), 1):
        parts = _tokens(raw)
        if not parts:
            continue
        key = parts[0].lower()
        where = '%s:%d' % (path, lineno)
        if key == 'limit':
            spec.limit = int(parts[1], 0)
            if not 1 <= spec.limit <= ENT_ABS_MAX:
                raise SystemExit('%s: limit 必须在 1..%d' % (where, ENT_ABS_MAX))
            continue
        if key == 'type':
            name = parts[1]
            if not name[0].isalpha() or not all(c.isalnum() or c == '_' for c in name):
                raise SystemExit('%s: 类型名 %s 需要是 C 标识符' % (where, name))
            if name in seen:
                raise SystemExit('%s: 类型 %s 重复' % (where, name))
            fields = {}
            for tok in parts[2:]:
                if '=' not in tok:
                    raise SystemExit('%s: 看不懂 %s' % (where, tok))
                k, v = tok.split('=', 1)
                fields[k] = int(v, 0)
            for need in ('id', 'w', 'h', 'pal'):
                if need not in fields:
                    raise SystemExit('%s: 类型 %s 缺少 %s' % (where, name, need))
            if fields['id'] in ids or not 1 <= fields['id'] <= 255:
                raise SystemExit('%s: id 必须是 1..255 且不能重复' % where)
            if not 1 <= fields['w'] <= 64 or not 1 <= fields['h'] <= 64 or not 0 <= fields['pal'] <= 3:
                raise SystemExit('%s: w/h 要在 1..64，调色板 0..3' % where)
            cur = EntityType(name, fields['id'], fields['w'], fields['h'], fields['pal'])
            spec.types.append(cur)
            seen.add(name)
            ids.add(fields['id'])
            continue
        if cur is None:
            raise SystemExit('%s: 还没有 type 行' % where)
        if key == 'label':
            cur.label = raw.split('#', 1)[0].split(None, 1)[1].strip()
            continue
        if key == 'sprite':
            if len(parts) != 4:
                raise SystemExit('%s: sprite dx dy tile' % where)
            cur.sprites.append((int(parts[1], 0), int(parts[2], 0), int(parts[3], 0) & 255))
            continue
        if key == 'prop':
            if len(parts) != 3:
                raise SystemExit('%s: prop 名字 默认值' % where)
            if len(cur.props) >= MAX_PROPS:
                raise SystemExit('%s: 每个类型最多 %d 个属性' % (where, MAX_PROPS))
            cur.props.append((parts[1], int(parts[2], 0) & 65535))
            continue
        raise SystemExit('%s: 未知关键字 %s' % (where, parts[0]))
    for t in spec.types:
        if not t.sprites:
            raise SystemExit('%s: 类型 %s 至少要一个 sprite' % (path, t.name))
    return spec


def save_types(path, spec):
    lines = [
        '# 实体类型。一张地图最多 limit 个（不能超过 32）。',
        '# type 名字 id= w= h= pal=',
        '#   label 中文名',
        '#   sprite dx dy tile',
        '#   prop 名字 默认值',
        'limit %d' % spec.limit,
        '',
    ]
    for t in spec.types:
        lines.append('type %s id=%d w=%d h=%d pal=%d' % (t.name, t.id, t.w, t.h, t.pal))
        if t.label:
            lines.append('  label %s' % t.label)
        for dx, dy, tile in t.sprites:
            lines.append('  sprite %d %d 0x%02X' % (dx, dy, tile))
        for name, default in t.props:
            lines.append('  prop %s %d' % (name, default))
        lines.append('')
    open(path, 'w').write('\n'.join(lines).rstrip() + '\n')


def parse_entity_line(line):
    parts = _tokens(line)
    if not parts:
        return None
    if len(parts) < 3:
        raise SystemExit('实体行需要「类型 x y」：%s' % line.strip())
    props = {}
    try:
        x, y = int(parts[1], 0), int(parts[2], 0)
        for tok in parts[3:]:
            if '=' not in tok:
                raise SystemExit('属性要写成 名字=数字：%s' % tok)
            k, v = tok.split('=', 1)
            props[k] = int(v, 0) & 65535
    except ValueError:
        raise SystemExit('数字看不懂：%s' % line.strip())
    return Entity(parts[0], x, y, props)


def entities_from_map_text(text, path='map'):
    mode = None
    found = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if raw.strip() in ('legend:', 'map:', 'palmap:', 'entities:'):
            mode = raw.strip()
            continue
        if mode != 'entities:':
            continue
        try:
            ent = parse_entity_line(raw)
        except SystemExit as exc:
            raise SystemExit('%s:%d: %s' % (path, lineno, exc))
        if ent is not None:
            found.append(ent)
    return found


def format_entities(entities, spec):
    if not entities:
        return ''
    lines = ['entities:']
    for ent in entities:
        bits = [ent.type, str(int(ent.x)), str(int(ent.y))]
        et = spec.by_name(ent.type) if spec else None
        names = [p[0] for p in et.props] if et else sorted(ent.props)
        for name in names:
            default = 0
            if et:
                default = dict(et.props).get(name, 0)
            bits.append('%s=%d' % (name, int(ent.props.get(name, default))))
        lines.append(' '.join(bits))
    return '\n'.join(lines) + '\n'


def pack(ent, spec):
    et = spec.by_name(ent.type)
    if et is None:
        raise SystemExit('没有类型 %s（检查 entities.txt）' % ent.type)
    if not 0 <= ent.x <= 65535 or not 0 <= ent.y <= 255:
        raise SystemExit('%s 坐标超出范围：(%d,%d)' % (ent.type, ent.x, ent.y))
    raw = [et.id & 255, ent.x & 255, (ent.x >> 8) & 255, ent.y & 255]
    known = set()
    for i in range(MAX_PROPS):
        if i < len(et.props):
            name, default = et.props[i]
            known.add(name)
            val = ent.props.get(name, default) & 65535
        else:
            val = 0
        raw.append(val & 255)
        raw.append((val >> 8) & 255)
    extra = set(ent.props) - known
    if extra:
        raise SystemExit('%s 没有属性 %s' % (ent.type, ', '.join(sorted(extra))))
    return raw


def check_count(entities, spec, where):
    if len(entities) > spec.limit:
        raise SystemExit('%s: 有 %d 个实体，上限是 %d。' % (where, len(entities), spec.limit))


def emit_map(spec, entities, name, where):
    check_count(entities, spec, where)
    rows = []
    for ent in entities:
        rows.append(','.join(str(b) for b in pack(ent, spec)))
    n = len(entities)
    up = name.upper()
    out = ['#define MAP_%s_ENT_N %d' % (up, n)]
    if n == 0:
        out.append('const unsigned char map_%s_ent[1] = {0};' % name)
    else:
        out.append('const unsigned char map_%s_ent[%d] = {' % (name, n * ENT_BYTES))
        for row in rows:
            out.append('  ' + row + ',')
        out.append('};')
    return '\n'.join(out)


def emit_game(game_dir):
    path = os.path.join(game_dir, 'entities.txt')
    if not os.path.exists(path):
        return ''
    spec = load_types(path)
    lines = ['/* GENERATED from entities.txt by tools/ent2c.py */',
             '#define ENT_LIMIT %d' % spec.limit]
    for t in spec.types:
        lines.append('#define ENT_%s %d' % (t.name.upper(), t.id))
    maps = []
    for fn in sorted(os.listdir(game_dir)):
        if not fn.endswith('.txt') or fn.lower() in ('songs.txt', 'palette.txt', 'entities.txt'):
            continue
        full = os.path.join(game_dir, fn)
        text = open(full).read()
        if '\nmap:' not in '\n' + text and not text.startswith('map:'):
            continue
        maps.append((os.path.splitext(fn)[0], entities_from_map_text(text, full), full))
    for name, ents, full in maps:
        lines.append(emit_map(spec, ents, name, full))
    return '\n'.join(lines) + '\n'


def main(game_dir):
    sys.stdout.write(emit_game(game_dir))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: ent2c.py games/<game>')
    main(sys.argv[1])
