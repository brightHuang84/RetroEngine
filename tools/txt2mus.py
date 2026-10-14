#!/usr/bin/env python3
"""Turn a human-writable song file into C89 tables (music.c / music.h).

  python3 tools/txt2mus.py games/<game>/songs.txt build/<game>/gen

The text format (also documented in README.md):

  song title          # becomes MUS_TITLE and song_title
  tempo 128           # quarter-note BPM; frames are derived so 8ths add up

  pulse1 duty 2 vol 10
    E5 8 G5 8 A5 8 R 8
    loop              # events above play once; events below loop
    C5 4

  pulse2 duty 1 vol 6
  triangle vol 15
  noise vol 5 mode 0  # mode 1 = short LFSR; N0..N15 are noise periods
    N1 8 R 8

Notes are C D E F G A B with optional # or b and an octave 1..7 (C4, Bb3).
R or - is a rest. Durations are note values (1 2 4 8 16 32); a trailing dot
is a dotted value (8.). t12 means exactly 12 frames. `once` on a channel
line plays that channel a single time. Channels loop from the start unless
`loop` or `once` is set. Keep channels the same length or their loops drift.
"""
import os
import sys

NOTE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
CHANS = {'pulse1': 0, 'pulse2': 1, 'triangle': 2, 'tri': 2, 'noise': 3}
CNAME = ['pulse1', 'pulse2', 'triangle', 'noise']


def quarter_frames(tempo):
    q = int(round(3600.0 / tempo))
    if q < 4:
        q = 4
    return q


def dur_frames(tok, quarter):
    dotted = tok.endswith('.')
    body = tok[:-1] if dotted else tok
    if body[:1].lower() == 't' and body[1:].isdigit():
        fr = int(body[1:])
    elif body.isdigit():
        denom = int(body)
        if denom <= 0:
            raise ValueError('bad duration %s' % tok)
        if dotted:
            fr = (quarter * 4 * 3) // (denom * 2)
        else:
            fr = (quarter * 4) // denom
    else:
        raise ValueError('bad duration %s' % tok)
    if fr < 1:
        fr = 1
    if fr > 255:
        fr = 255
    return fr


def parse_pitch(tok):
    t = tok.strip()
    if t.upper() in ('R', '-', '.'):
        return 0
    u = t.upper()
    if u[0] == 'N':
        n = int(u[1:], 10)
        if n < 0 or n > 15:
            raise ValueError('noise %s out of N0..N15' % t)
        return n + 1
    if u[0] not in NOTE:
        raise ValueError('bad note %s' % t)
    i = 1
    acc = 0
    if i < len(u) and u[i] == '#':
        acc = 1
        i += 1
    elif i < len(u) and u[i] == 'B':
        acc = -1
        i += 1
    if i >= len(u) or not u[i:].isdigit():
        raise ValueError('bad note %s' % t)
    octave = int(u[i:])
    if octave < 1 or octave > 7:
        raise ValueError('octave out of 1..7 in %s' % t)
    semi = NOTE[u[0]] + acc
    idx = (octave - 1) * 12 + semi + 1
    if idx < 1 or idx > 84:
        raise ValueError('note %s is outside C1..B7' % t)
    return idx


class Chan(object):
    def __init__(self):
        self.duty = 2
        self.vol = 10
        self.once = False
        self.events = []          # (note, dur)
        self.loop_at = None       # event index, None = whole channel


class Song(object):
    def __init__(self, name):
        self.name = name
        self.tempo = 120
        self.ch = [None, None, None, None]


def strip_comment(line):
    """'#' starts a comment only when it is its own token, so F#4 and C#4 stay notes."""
    out = []
    i = 0
    while i < len(line):
        if line[i] == '#' and (i == 0 or line[i - 1].isspace()):
            break
        out.append(line[i])
        i += 1
    return ''.join(out).strip()


def parse(path):
    songs = []
    cur = None
    chan = None
    line_no = 0
    for raw in open(path):
        line_no += 1
        line = strip_comment(raw)
        if not line or line.startswith(';'):
            continue
        parts = line.split()
        key = parts[0].lower()
        try:
            if key == 'song':
                if len(parts) != 2 or not parts[1].replace('_', '').isalnum():
                    raise ValueError('song needs a name')
                cur = Song(parts[1])
                songs.append(cur)
                chan = None
                continue
            if cur is None:
                raise ValueError('expected song <name>')
            if key == 'tempo':
                cur.tempo = int(parts[1])
                if cur.tempo < 30 or cur.tempo > 300:
                    raise ValueError('tempo out of 30..300')
                continue
            if key in CHANS:
                chan = Chan()
                cur.ch[CHANS[key]] = chan
                i = 1
                while i < len(parts):
                    k = parts[i].lower()
                    if k == 'once':
                        chan.once = True
                        i += 1
                        continue
                    if i + 1 >= len(parts):
                        raise ValueError('missing value after %s' % k)
                    if k == 'duty':
                        chan.duty = int(parts[i + 1])
                    elif k == 'vol':
                        chan.vol = int(parts[i + 1])
                    elif k == 'mode':
                        chan.duty = int(parts[i + 1])
                    else:
                        raise ValueError('unknown channel option %s' % k)
                    i += 2
                if not (0 <= chan.duty <= 3 and 0 <= chan.vol <= 15):
                    raise ValueError('duty 0..3, vol 0..15, mode 0..1')
                continue
            if key == 'loop':
                if chan is None:
                    raise ValueError('loop outside a channel')
                if chan.loop_at is not None:
                    raise ValueError('two loop points')
                chan.loop_at = len(chan.events)
                continue
            if chan is None:
                raise ValueError('notes need a channel first')
            if len(parts) % 2:
                raise ValueError('notes must be pairs: C4 8')
            q = quarter_frames(cur.tempo)
            idx = CHANS_INDEX(cur, chan)
            for n in range(0, len(parts), 2):
                tok = parts[n]
                utok = tok.upper()
                if idx == 3 and utok not in ('R', '-', '.') and not (utok[:1] == 'N' and utok[1:].isdigit()):
                    raise ValueError('noise channel wants N0..N15 or R, not %s' % tok)
                if idx != 3 and utok[:1] == 'N' and utok[1:2].isdigit():
                    raise ValueError('%s belongs on the noise channel' % tok)
                pitch = parse_pitch(tok)
                frames = dur_frames(parts[n + 1], q)
                chan.events.append((pitch, frames))
        except (ValueError, IndexError) as e:
            sys.exit('%s:%d: %s' % (path, line_no, e))
    if not songs:
        sys.exit('%s: no songs' % path)
    return songs


def CHANS_INDEX(song, chan):
    for i, c in enumerate(song.ch):
        if c is chan:
            return i
    return -1


def frames_of(ch):
    return sum(d for _, d in ch.events)


def emit(songs, out_dir, src_name):
    c = []
    h = []
    c.append('/* GENERATED by tools/txt2mus.py from %s. Do not edit. */' % src_name)
    c.append('#include "music.h"')
    h.append('/* GENERATED by tools/txt2mus.py from %s. Do not edit. */' % src_name)
    h.append('#ifndef MUSIC_H')
    h.append('#define MUSIC_H')
    h.append('#include "engine/engine.h"')
    for si, song in enumerate(songs):
        macro = 'MUS_' + song.name.upper()
        h.append('#define %s %d' % (macro, si))
        q = quarter_frames(song.tempo)
        c.append('/* song %s  tempo %d  quarter %d frames */' % (song.name, song.tempo, q))
        lengths = []
        ptrs = ['0', '0', '0', '0']
        for ci, ch in enumerate(song.ch):
            if ch is None or not ch.events:
                continue
            base = 'mus_%s_%s' % (song.name, CNAME[ci])
            data = []
            loop = 0
            if ch.once:
                loop = 0xFFFF
            elif ch.loop_at:
                loop = ch.loop_at * 2
            for note, dur in ch.events:
                data.append(note)
                data.append(dur)
            data.append(255)
            c.append('static const u8 %s[] = {' % base)
            line = []
            for i, b in enumerate(data):
                line.append(str(b))
                if len(line) == 16 or i + 1 == len(data):
                    c.append('  ' + ','.join(line) + ',')
                    line = []
            c.append('};')
            c.append('static const Track %s_tr = { %s, %d, %d, %d };' % (base, base, loop, ch.duty & 3, ch.vol))
            ptrs[ci] = '&%s_tr' % base
            lengths.append((CNAME[ci], frames_of(ch)))
        if lengths:
            base_len = lengths[0][1]
            for name, n in lengths[1:]:
                if n != base_len:
                    sys.stderr.write('warning: %s channel %s is %d frames, %s is %d (loops will drift)\n' % (
                        song.name, lengths[0][0], base_len, name, n))
        c.append('static const Song song_%s = { { %s } };' % (song.name, ', '.join(ptrs)))
    h.append('#define MUS_COUNT %d' % len(songs))
    h.append('#endif')
    c.append('const Song *music_lookup(u8 id){')
    for si, song in enumerate(songs):
        c.append('  if(id == %d) return &song_%s;' % (si, song.name))
    c.append('  return 0;')
    c.append('}')
    c.append('')
    open(os.path.join(out_dir, 'music.c'), 'w').write('\n'.join(c) + '\n')
    open(os.path.join(out_dir, 'music.h'), 'w').write('\n'.join(h) + '\n')


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: txt2mus.py <songs.txt> <out-dir>')
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    songs = parse(src)
    emit(songs, out, os.path.basename(src))
    print('music -> %s (%d songs)' % (out, len(songs)))


if __name__ == '__main__':
    main()
