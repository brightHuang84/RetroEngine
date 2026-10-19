#!/usr/bin/env python3
"""Compile games/<game>/scripts.json into scriptdata.c and scripts.h.

The bytecode is a stack-free program the engine VM runs. Missing file -> empty
program, so games without scripts still link.
"""
import json
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import ent2c

# Keep these numbers in sync with engine/script.c
OP_END, OP_SET, OP_ADD, OP_SFX, OP_MUS = 0, 1, 2, 3, 4
OP_WAIT, OP_SHAKE, OP_DESPAWN, OP_SPAWN, OP_ANIM = 5, 6, 7, 8, 9
OP_LEVEL, OP_WIN, OP_HURT, OP_LOSE, OP_TEXT = 10, 11, 12, 13, 14
OP_JMP, OP_JEQ, OP_JNE, OP_JLT, OP_JGT = 15, 16, 17, 18, 19
OP_JEQV, OP_RAND, OP_HOOK, OP_MOVE, OP_TIMER = 20, 21, 22, 23, 24
OP_ACTOR, OP_JNHELD, OP_SCENE = 25, 26, 27

SEV_BOOT, SEV_LEVEL, SEV_FRAME, SEV_BUTTON = 1, 2, 3, 4
SEV_TOUCH, SEV_TILE, SEV_ENTITY, SEV_TIMER = 5, 6, 7, 8
SEV_VAR, SEV_REGION = 9, 10

EVENTS = (
    ('boot', '游戏开始', SEV_BOOT),
    ('level', '关卡开始', SEV_LEVEL),
    ('frame', '每帧', SEV_FRAME),
    ('button', '按下按键', SEV_BUTTON),
    ('touch', '玩家碰到实体', SEV_TOUCH),
    ('tile', '实体碰到图块', SEV_TILE),
    ('entity', '实体碰到实体', SEV_ENTITY),
    ('timer', '计时器', SEV_TIMER),
    ('var', '变量条件', SEV_VAR),
    ('region', '进入区域', SEV_REGION),
)
EVENT_BY_NAME = {e[0]: e for e in EVENTS}

OPS = (
    ('set', '设置变量'),
    ('add', '变量加上'),
    ('sfx', '播放音效'),
    ('music', '播放音乐'),
    ('music_stop', '停止音乐'),
    ('despawn', '删除实体'),
    ('spawn', '生成实体'),
    ('move', '移动实体'),
    ('anim', '切换动画'),
    ('level', '跳到关卡'),
    ('scene', '切换场景'),
    ('text', '显示文字'),
    ('wait', '等待'),
    ('shake', '摇镜头'),
    ('hurt', '生命减一'),
    ('win', '过关'),
    ('lose', '游戏结束'),
    ('advance', '下一关'),
    ('if', '如果'),
    ('repeat', '重复'),
    ('rand', '随机'),
    ('hook', '调用函数'),
    ('timer', '启动计时器'),
    ('actor', '放置角色'),
)
OP_LABEL = dict(OPS)

SFX = {'blip': 1, 'hit': 2, 'coin': 3, 'jump': 4, 'lose': 5, 'win': 6}
BUTTONS = {'right': 0x01, 'left': 0x02, 'down': 0x04, 'up': 0x08,
           'start': 0x10, 'select': 0x20, 'b': 0x40, 'a': 0x80}
SCENES = {'title': 0, 'play': 1, 'end': 2}
CMPS = ('eq', 'ne', 'lt', 'gt', 'held')


def empty_doc():
    return {
        'variables': [],
        'strings': [],
        'hooks': [],
        'regions': [],
        'scripts': [],
    }


def load(path):
    if not path or not os.path.isfile(path):
        return empty_doc()
    doc = json.loads(open(path, encoding='utf-8').read())
    base = empty_doc()
    for key in base:
        if key in doc:
            base[key] = doc[key]
    return base


def dump(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + '\n'


def new_block(op):
    block = {'op': op}
    if op in ('set', 'add'):
        block['var'] = ''
        block['value'] = 0
    elif op == 'sfx':
        block['id'] = 'coin'
    elif op == 'music':
        block['id'] = ''
    elif op == 'spawn':
        block['entity'] = ''
        block['x'] = 0
        block['y'] = 0
    elif op == 'move':
        block['actor'] = 0
        block['dx'] = 1
        block['dy'] = 0
    elif op == 'anim':
        block['actor'] = 0
        block['id'] = ''
    elif op == 'level':
        block['id'] = 'next'
    elif op == 'scene':
        block['id'] = 'play'
    elif op == 'text':
        block['text'] = ''
        block['frames'] = 90
    elif op in ('wait', 'shake'):
        block['frames'] = 30
    elif op == 'if':
        block['cmp'] = 'eq'
        block['var'] = ''
        block['value'] = 0
        block['var2'] = ''
        block['button'] = 'right'
        block['then'] = []
        block['else'] = []
    elif op == 'repeat':
        block['count'] = 2
        block['body'] = []
    elif op == 'rand':
        block['var'] = ''
        block['max'] = 2
    elif op == 'hook':
        block['id'] = ''
        block['arg'] = 0
    elif op == 'timer':
        block['id'] = 0
        block['frames'] = 60
    elif op == 'actor':
        block['actor'] = 0
        block['entity'] = ''
        block['x'] = 0
        block['y'] = 0
        block['anim'] = ''
    return block


def new_script():
    return {
        'name': '新脚本',
        'event': 'frame',
        'level': '',
        'entity': '',
        'button': 'a',
        'timer': 0,
        'var': '',
        'value': 0,
        'region': '',
        'tile': 0,
        'other': '',
        'blocks': [],
    }


class CompileError(Exception):
    pass


def _songs(game_dir):
    path = os.path.join(game_dir, 'songs.txt')
    names = []
    if os.path.isfile(path):
        for line in open(path, encoding='utf-8'):
            parts = line.split('#', 1)[0].split()
            if len(parts) >= 2 and parts[0] == 'song':
                names.append(parts[1])
    return names


def _levels(game_dir):
    path = os.path.join(game_dir, 'maps', 'order.txt')
    names = []
    if os.path.isfile(path):
        for line in open(path, encoding='utf-8'):
            name = line.split('#', 1)[0].strip()
            if name:
                names.append(name)
    return names


def _anims(game_dir):
    path = os.path.join(game_dir, 'anims.json')
    if not os.path.isfile(path):
        return []
    doc = json.loads(open(path, encoding='utf-8').read())
    return [a.get('name', '') for a in doc.get('anims', [])]


def context(game_dir):
    types = {}
    path = os.path.join(game_dir, 'entities.txt')
    if os.path.isfile(path):
        spec = ent2c.load_types(path)
        for t in spec.types:
            types[t.name] = t.id
    return {
        'entities': types,
        'songs': _songs(game_dir),
        'anims': _anims(game_dir),
        'levels': _levels(game_dir),
    }


def _u16(n):
    n &= 65535
    return [n & 255, (n >> 8) & 255]


def _s16(n):
    if n < 0:
        n += 65536
    return _u16(n)


class _Out(object):
    def __init__(self):
        self.buf = []
        self.labels = {}
        self.patches = []  # (at, label)

    def emit(self, *vals):
        for v in vals:
            self.buf.append(v & 255)

    def label(self, name):
        self.labels[name] = len(self.buf)

    def jump(self, op, name):
        self.emit(op)
        self.patches.append((len(self.buf), name))
        self.emit(0, 0)

    def patch(self):
        for at, name in self.patches:
            dest = self.labels[name]
            self.buf[at] = dest & 255
            self.buf[at + 1] = (dest >> 8) & 255


def check(doc, ctx, where='脚本'):
    """Return a list of Chinese error strings. Empty means the doc compiles."""
    errors = []
    globals_, levels = [], []
    for var in doc.get('variables', []):
        name = var.get('name', '')
        if not name:
            errors.append('有一个变量没有名字')
            continue
        scope = var.get('scope', 'global')
        bucket = globals_ if scope != 'level' else levels
        if name in globals_ or name in levels:
            errors.append('变量 %s 重复了' % name)
        bucket.append(name)
        size = var.get('size', 'u16')
        init = int(var.get('init', 0) or 0)
        if size == 'u8' and not 0 <= init <= 255:
            errors.append('变量 %s 是 u8，初值要在 0 到 255' % name)
        if size == 'u16' and not 0 <= init <= 65535:
            errors.append('变量 %s 的初值超出 u16' % name)
    if len(globals_) > 8:
        errors.append('全局变量最多 8 个，现在有 %d 个' % len(globals_))
    if len(levels) > 8:
        errors.append('本关变量最多 8 个，现在有 %d 个' % len(levels))
    known = set(globals_) | set(levels)
    strings = list(doc.get('strings', []))
    hooks = list(doc.get('hooks', []))
    regions = [r.get('name', '') for r in doc.get('regions', [])]
    entities = ctx.get('entities', {})
    songs = set(ctx.get('songs', []))
    anims = set(ctx.get('anims', []))
    levels_names = ctx.get('levels', [])

    def var_of(script, name):
        if name not in known:
            errors.append('脚本「%s」：未知变量 %s' % (script, name or '（空）'))

    def walk(script, blocks):
        for block in blocks or []:
            op = block.get('op')
            if op not in OP_LABEL:
                errors.append('脚本「%s」：不认识的积木 %s' % (script, op))
                continue
            if op in ('set', 'add', 'rand'):
                var_of(script, block.get('var', ''))
            if op == 'sfx' and block.get('id', 'coin') not in SFX:
                errors.append('脚本「%s」：未知音效 %s' % (script, block.get('id')))
            if op == 'music' and block.get('id') not in songs:
                errors.append('脚本「%s」：未知乐曲 %s' % (script, block.get('id')))
            if op == 'spawn' and block.get('entity') not in entities:
                errors.append('脚本「%s」：未知实体 %s' % (script, block.get('entity')))
            if op == 'anim' and block.get('id') not in anims:
                errors.append('脚本「%s」：未知动画 %s' % (script, block.get('id')))
            if op == 'actor':
                if block.get('entity') and block.get('entity') not in entities:
                    errors.append('脚本「%s」：未知实体 %s' % (script, block.get('entity')))
                if block.get('anim') and block.get('anim') not in anims:
                    errors.append('脚本「%s」：未知动画 %s' % (script, block.get('anim')))
            if op == 'level' and block.get('id') not in ('next', '') and block.get('id') not in levels_names:
                errors.append('脚本「%s」：未知关卡 %s' % (script, block.get('id')))
            if op == 'scene' and block.get('id', 'play') not in SCENES:
                errors.append('脚本「%s」：场景要是 title、play 或 end' % script)
            if op == 'text' and not str(block.get('text', '')).strip():
                errors.append('脚本「%s」：显示文字是空的' % script)
            if op == 'hook' and block.get('id') not in hooks:
                errors.append('脚本「%s」：未知函数 %s' % (script, block.get('id') or '（空）'))
            if op == 'repeat':
                n = int(block.get('count', 0) or 0)
                if not 1 <= n <= 8:
                    errors.append('脚本「%s」：重复次数要在 1 到 8' % script)
                walk(script, block.get('body') or [])
            if op == 'if':
                cmp_ = block.get('cmp', 'eq')
                if cmp_ not in CMPS:
                    errors.append('脚本「%s」：比较方式不认识' % script)
                if cmp_ == 'held':
                    if block.get('button', 'right') not in BUTTONS:
                        errors.append('脚本「%s」：未知按键' % script)
                else:
                    var_of(script, block.get('var', ''))
                    if block.get('var2'):
                        var_of(script, block.get('var2'))
                        if cmp_ != 'eq':
                            errors.append('脚本「%s」：两个变量只能比较是否相等' % script)
                walk(script, block.get('then') or [])
                walk(script, block.get('else') or [])
            if op in ('wait', 'shake', 'timer'):
                frames = int(block.get('frames', 0) or 0)
                if not 0 <= frames <= 255:
                    errors.append('脚本「%s」：帧数要在 0 到 255' % script)

    for script in doc.get('scripts', []):
        name = script.get('name') or '未命名'
        ev = script.get('event', 'frame')
        if ev not in EVENT_BY_NAME:
            errors.append('脚本「%s」：未知事件 %s' % (name, ev))
        if ev == 'touch' and script.get('entity') not in entities:
            errors.append('脚本「%s」：未知实体 %s' % (name, script.get('entity')))
        if ev == 'entity' and script.get('other') not in entities:
            errors.append('脚本「%s」：未知实体 %s' % (name, script.get('other')))
        if ev == 'button' and script.get('button', 'a') not in BUTTONS:
            errors.append('脚本「%s」：未知按键' % name)
        if ev == 'var':
            var_of(name, script.get('var', ''))
        if ev == 'region' and script.get('region') not in regions:
            errors.append('脚本「%s」：未知区域 %s' % (name, script.get('region')))
        if script.get('level') and script.get('level') not in levels_names:
            errors.append('脚本「%s」：未知关卡 %s' % (name, script.get('level')))
        walk(name, script.get('blocks') or [])
    if len(doc.get('scripts', [])) > 32:
        errors.append('脚本最多 32 个')
    if len(strings) > 16:
        errors.append('文字最多 16 条')
    return errors


def _scope_index(name, gnames, lnames):
    if name in gnames:
        return 0, gnames.index(name)
    return 1, lnames.index(name)


def compile_doc(doc, ctx):
    errors = check(doc, ctx)
    if errors:
        raise CompileError('\n'.join(errors))
    gnames, lnames = [], []
    ginits = [0] * 8
    linits = [0] * 8
    for var in doc.get('variables', []):
        if var.get('scope') == 'level':
            linits[len(lnames)] = int(var.get('init', 0) or 0) & 65535
            lnames.append(var['name'])
        else:
            ginits[len(gnames)] = int(var.get('init', 0) or 0) & 65535
            gnames.append(var['name'])
    strings = [str(s) for s in doc.get('strings', [])]
    # Text blocks may introduce strings that were not listed.
    hooks = list(doc.get('hooks', []))
    entities = ctx.get('entities', {})
    songs = ctx.get('songs', [])
    anims = ctx.get('anims', [])
    levels = ctx.get('levels', [])
    regions = doc.get('regions', [])

    def ensure_string(text):
        if text not in strings:
            strings.append(text)
        return strings.index(text)

    out = _Out()
    entries = []
    metas = []
    serial = [0]

    def fresh():
        serial[0] += 1
        return 'L%d' % serial[0]

    def emit_blocks(blocks):
        for block in blocks or []:
            op = block.get('op')
            if op in ('set', 'add'):
                scope, idx = _scope_index(block.get('var', ''), gnames, lnames)
                value = int(block.get('value', 0) or 0)
                out.emit(OP_SET if op == 'set' else OP_ADD, scope, idx)
                out.emit(*( _u16(value) if op == 'set' else _s16(value)))
            elif op == 'sfx':
                out.emit(OP_SFX, SFX[block.get('id', 'coin')])
            elif op == 'music':
                out.emit(OP_MUS, songs.index(block.get('id')))
            elif op == 'music_stop':
                out.emit(OP_MUS, 255)
            elif op == 'despawn':
                out.emit(OP_DESPAWN)
            elif op == 'spawn':
                x = int(block.get('x', 0) or 0)
                out.emit(OP_SPAWN, entities[block.get('entity')], x & 255, (x >> 8) & 255, int(block.get('y', 0) or 0) & 255)
            elif op == 'move':
                out.emit(OP_MOVE, int(block.get('actor', 0) or 0) & 255,
                         int(block.get('dx', 0) or 0) & 255, int(block.get('dy', 0) or 0) & 255)
            elif op == 'anim':
                out.emit(OP_ANIM, int(block.get('actor', 0) or 0) & 255, anims.index(block.get('id')))
            elif op == 'level':
                name = block.get('id') or 'next'
                if name == 'next':
                    out.emit(OP_LEVEL, 254)
                else:
                    out.emit(OP_LEVEL, levels.index(name) & 255)
            elif op == 'scene':
                out.emit(OP_SCENE, SCENES[block.get('id', 'play')])
            elif op == 'text':
                out.emit(OP_TEXT, ensure_string(str(block.get('text', ''))), int(block.get('frames', 90) or 0) & 255)
            elif op == 'wait':
                out.emit(OP_WAIT, int(block.get('frames', 1) or 1) & 255)
            elif op == 'shake':
                out.emit(OP_SHAKE, int(block.get('frames', 1) or 1) & 255)
            elif op == 'hurt':
                out.emit(OP_HURT)
            elif op == 'win':
                out.emit(OP_WIN)
            elif op == 'lose':
                out.emit(OP_LOSE)
            elif op == 'advance':
                out.emit(OP_LEVEL, 254)
            elif op == 'rand':
                scope, idx = _scope_index(block.get('var', ''), gnames, lnames)
                out.emit(OP_RAND, scope, idx, int(block.get('max', 2) or 2) & 255)
            elif op == 'hook':
                out.emit(OP_HOOK, hooks.index(block.get('id')), int(block.get('arg', 0) or 0) & 255)
            elif op == 'timer':
                out.emit(OP_TIMER, int(block.get('id', 0) or 0) & 1, int(block.get('frames', 1) or 1) & 255)
            elif op == 'actor':
                x = int(block.get('x', 0) or 0)
                anim = anims.index(block['anim']) if block.get('anim') else 255
                et = entities.get(block.get('entity'), 0)
                out.emit(OP_ACTOR, int(block.get('actor', 0) or 0) & 255, et, x & 255, (x >> 8) & 255,
                         int(block.get('y', 0) or 0) & 255, anim)
            elif op == 'repeat':
                for _ in range(int(block.get('count', 1) or 1)):
                    emit_blocks(block.get('body') or [])
            elif op == 'if':
                else_l, end_l = fresh(), fresh()
                emit_if_false(block, else_l)
                emit_blocks(block.get('then') or [])
                out.jump(OP_JMP, end_l)
                out.label(else_l)
                emit_blocks(block.get('else') or [])
                out.label(end_l)

    def emit_if_false(block, dest):
        cmp_ = block.get('cmp', 'eq')
        if cmp_ == 'held':
            out.emit(OP_JNHELD, BUTTONS[block.get('button', 'right')])
            out.patches.append((len(out.buf), dest))
            out.emit(0, 0)
            return
        scope, idx = _scope_index(block.get('var', ''), gnames, lnames)
        if block.get('var2'):
            sb, ib = _scope_index(block.get('var2'), gnames, lnames)
            then_l = fresh()
            out.emit(OP_JEQV, scope, idx, sb, ib)
            out.patches.append((len(out.buf), then_l))
            out.emit(0, 0)
            out.jump(OP_JMP, dest)
            out.label(then_l)
            return
        value = int(block.get('value', 0) or 0)
        op = {'eq': OP_JNE, 'ne': OP_JEQ, 'lt': OP_JGT, 'gt': OP_JLT}[cmp_]
        # Jump when the condition is FALSE: eq fails -> JNE, ne fails -> JEQ,
        # lt fails when var > value OR var == value. JGT catches var > value only.
        # For lt, false means var >= value. We don't have JGE. Emit JEQ to dest
        # OR JGT to dest. Two jumps.
        if cmp_ == 'lt':
            out.emit(OP_JEQ, scope, idx)
            out.emit(*_u16(value))
            out.patches.append((len(out.buf), dest))
            out.emit(0, 0)
            out.emit(OP_JGT, scope, idx)
            out.emit(*_u16(value))
            out.patches.append((len(out.buf), dest))
            out.emit(0, 0)
            return
        if cmp_ == 'gt':
            out.emit(OP_JEQ, scope, idx)
            out.emit(*_u16(value))
            out.patches.append((len(out.buf), dest))
            out.emit(0, 0)
            out.emit(OP_JLT, scope, idx)
            out.emit(*_u16(value))
            out.patches.append((len(out.buf), dest))
            out.emit(0, 0)
            return
        out.emit(op, scope, idx)
        out.emit(*_u16(value))
        out.patches.append((len(out.buf), dest))
        out.emit(0, 0)

    for script in doc.get('scripts', []):
        ev = EVENT_BY_NAME[script.get('event', 'frame')][2]
        arg = 0
        extra = 0
        if script.get('event') == 'touch':
            arg = entities[script.get('entity')]
        elif script.get('event') == 'entity':
            arg = entities[script.get('other')]
        elif script.get('event') == 'button':
            arg = BUTTONS[script.get('button', 'a')]
        elif script.get('event') == 'timer':
            arg = int(script.get('timer', 0) or 0) & 1
        elif script.get('event') == 'var':
            scope, idx = _scope_index(script.get('var', ''), gnames, lnames)
            arg = idx | (scope << 7)
            extra = int(script.get('value', 0) or 0) & 255
        elif script.get('event') == 'region':
            arg = [r.get('name', '') for r in regions].index(script.get('region'))
        elif script.get('event') == 'tile':
            arg = int(script.get('tile', 0) or 0) & 255
        level = 255
        if script.get('level'):
            level = levels.index(script['level'])
        entries.append(len(out.buf))
        metas.append((ev, arg, level, extra))
        emit_blocks(script.get('blocks') or [])
        out.emit(OP_END)
    out.patch()
    region_bytes = []
    for i, region in enumerate(regions):
        x = int(region.get('x', 0) or 0)
        region_bytes += [i, 255, x & 255, (x >> 8) & 255,
                         int(region.get('y', 0) or 0) & 255,
                         int(region.get('w', 16) or 16) & 255,
                         int(region.get('h', 16) or 16) & 255]
    return {
        'code': out.buf,
        'metas': metas,
        'entries': entries,
        'ginits': ginits,
        'linits': linits,
        'gnames': gnames,
        'lnames': lnames,
        'strings': strings,
        'hooks': hooks,
        'regions': region_bytes,
    }


def _c_bytes(data, per=16):
    if not data:
        return '  0'
    lines = []
    for i in range(0, len(data), per):
        lines.append('  ' + ','.join(str(b) for b in data[i:i + per]) + ',')
    return '\n'.join(lines)


def emit_sources(doc, ctx):
    prog = compile_doc(doc, ctx)
    code = prog['code'] or [0]
    meta = []
    for (ev, arg, level, extra), entry in zip(prog['metas'], prog['entries']):
        meta += [ev, arg, level, extra, entry & 255, (entry >> 8) & 255]
    if not meta:
        meta = [0]
    regions = prog['regions'] or [0]
    strings = prog['strings']
    c = []
    c.append('/* GENERATED by tools/scriptc.py */')
    c.append('#include "engine/engine.h"')
    c.append('const unsigned char sdata[%d] = {' % len(code))
    c.append(_c_bytes(code))
    c.append('};')
    c.append('const unsigned short slen = %d;' % len(prog['code']))
    c.append('const unsigned char smeta[%d] = {' % len(meta))
    c.append(_c_bytes(meta))
    c.append('};')
    c.append('const unsigned char scount = %d;' % len(prog['metas']))
    c.append('const unsigned short sginit[8] = {%s};' % ','.join(str(v) for v in prog['ginits']))
    c.append('const unsigned short slinit[8] = {%s};' % ','.join(str(v) for v in prog['linits']))
    if strings:
        for i, text in enumerate(strings):
            c.append('static const char str_%d[] = %s;' % (i, _cstr(text)))
        c.append('const char *const stext[%d] = {%s};' % (
            len(strings), ','.join('str_%d' % i for i in range(len(strings)))))
        c.append('const unsigned char sntext = %d;' % len(strings))
    else:
        c.append('const char *const stext[1] = {0};')
        c.append('const unsigned char sntext = 0;')
    c.append('const unsigned char sregion[%d] = {' % len(regions))
    c.append(_c_bytes(regions))
    c.append('};')
    c.append('const unsigned char snregion = %d;' % (len(prog['regions']) // 7))
    h = ['/* GENERATED by tools/scriptc.py */', '#ifndef SCRIPTS_H', '#define SCRIPTS_H']
    for i, name in enumerate(prog['gnames']):
        h.append('#define VAR_%s %d' % (_ident(name), i))
        h.append('#define VS_%s 0' % _ident(name))
    for i, name in enumerate(prog['lnames']):
        h.append('#define VAR_%s %d' % (_ident(name), i))
        h.append('#define VS_%s 1' % _ident(name))
    for i, name in enumerate(prog['hooks']):
        h.append('#define HOOK_%s %d' % (_ident(name), i))
    h.append('#endif')
    # Drop the accidental empty append above.
    c = [line for line in c if line != '']
    return '\n'.join(c) + '\n', '\n'.join(h) + '\n'


def _ident(name):
    out = []
    for ch in name:
        if ch.isalnum() and ord(ch) < 128:
            out.append(ch.upper())
        else:
            out.append('_')
    text = ''.join(out).strip('_') or 'V'
    if text[0].isdigit():
        text = 'V' + text
    return text


def _cstr(text):
    raw = text.replace('\\', '\\\\').replace('"', '\\"')
    return '"%s"' % raw


def write(game_dir, out_dir):
    path = os.path.join(game_dir, 'scripts.json')
    doc = load(path)
    ctx = context(game_dir)
    c_text, h_text = emit_sources(doc, ctx)
    open(os.path.join(out_dir, 'scriptdata.c'), 'w').write(c_text)
    open(os.path.join(out_dir, 'scripts.h'), 'w').write(h_text)


def main(argv):
    if len(argv) == 3 and argv[2] == '--check':
        doc = load(argv[1] if argv[1].endswith('.json') else os.path.join(argv[1], 'scripts.json'))
        game = argv[1] if os.path.isdir(argv[1]) else os.path.dirname(argv[1])
        errors = check(doc, context(game))
        if errors:
            sys.stderr.write('\n'.join(errors) + '\n')
            return 1
        print('脚本检查通过')
        return 0
    if len(argv) != 3:
        sys.exit('usage: scriptc.py games/<game> build/<game>/gen')
    write(argv[1], argv[2])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
