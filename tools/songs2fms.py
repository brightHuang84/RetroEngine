#!/usr/bin/env python3
"""Export songs.txt to FamiStudio text (File > Export > FamiStudio Text).

  python3 tools/songs2fms.py games/breakout/songs.txt games/breakout/fami/breakout.fms.txt

Open the result in FamiStudio, edit it, then export FamiStudio Text into
games/<game>/music/<name>.fms.txt. Files under fami/ are not imported by
make, so this starting point does not duplicate the songs already in
songs.txt.

Pitches, frame lengths, duty, volume and the song loop point are kept.
The groove is a single value (no swing), so each note lands on a cell and
the frame count matches the engine. A pattern is split when FamiStudio's
pattern-length check would reject it, and the loop point is placed on a
pattern boundary.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import txt2mus

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
CHANS = ['Square1', 'Square2', 'Triangle', 'Noise']
# Importer rejects patternLength * noteLength > floor(Pattern.MaxLength / noteLength).
PATTERN_MAX = 2048


def pitch_name(idx, noise):
    if idx <= 0:
        return None
    n = idx - 1
    if noise:
        n = max(0, min(15, n))
        return NOTE_NAMES[n % 12] + str(n // 12)
    if n > 83:
        n = 83
    return NOTE_NAMES[n % 12] + str(n // 12 + 1)


def channel_grid(ch):
    grid = []
    loop_at = None
    t = 0
    if ch is None:
        return grid, None
    if ch.once:
        loop_at = 'once'
    for i, (note, dur) in enumerate(ch.events):
        if loop_at != 'once' and ch.loop_at is not None and i == ch.loop_at:
            loop_at = t
        for _ in range(dur):
            grid.append(note)
        t += dur
    if loop_at != 'once' and ch.loop_at is not None and ch.loop_at >= len(ch.events):
        loop_at = t
    if loop_at is None:
        loop_at = 0
    return grid, loop_at


def choose_step(total, marks):
    if total <= 0:
        return 1
    g = total
    for m in marks:
        if m:
            g = _gcd(g, m)
    if g < 1:
        g = 1
    step = 1
    for d in range(1, 19):
        if g % d == 0:
            step = d
    return step


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def max_notes(step):
    cap = PATTERN_MAX // step
    n = cap // step
    if n < 1:
        n = 1
    return n


def chunk_range(start, end, size):
    out = []
    t = start
    while t < end:
        nxt = t + size
        if nxt > end:
            nxt = end
        out.append((t, nxt))
        t = nxt
    return out


def split_song(total, step, loop_frame):
    """Return (ranges, loop_column). loop_column -1 means play once."""
    size = max_notes(step) * step
    if loop_frame == 'once':
        return chunk_range(0, total, size), -1
    if not loop_frame or loop_frame <= 0 or loop_frame >= total:
        return chunk_range(0, total, size), 0
    intro = chunk_range(0, loop_frame, size)
    loop = chunk_range(loop_frame, total, size)
    return intro + loop, len(intro)


def instrument_name(ci, duty, vol):
    if ci == 2:
        return 'tri_v%d' % vol
    if ci == 3:
        return 'noise_m%d_v%d' % (duty & 1, vol)
    return 'sq%d_d%d_v%d' % (ci + 1, duty & 3, vol)


def emit_notes(lines, grid, start, end, inst, noise):
    i = start
    while i < end:
        tok = grid[i]
        j = i + 1
        while j < end and grid[j] == tok:
            j += 1
        name = pitch_name(tok, noise)
        if name:
            lines.append('\t\t\t\tNote Time="%d" Value="%s" Duration="%d" Instrument="%s"' % (
                i - start, name, j - i, inst))
        i = j


def export(songs, title):
    lines = []
    lines.append('Project Version="4.5.3" TempoMode="FamiStudio" Name="%s" Author="RetroEngine"' % title)
    inst_lines = []
    seen_inst = set()
    song_blocks = []
    for song in songs:
        grids = []
        loops = []
        duties = []
        vols = []
        for ci in range(4):
            ch = song.ch[ci]
            grid, loop_at = channel_grid(ch)
            grids.append(grid)
            loops.append(loop_at)
            if ch is None:
                duties.append(2 if ci < 2 else 0)
                vols.append(10 if ci < 2 else (15 if ci == 2 else 6))
            else:
                duties.append(ch.duty)
                vols.append(ch.vol)
        total = 0
        for g in grids:
            if len(g) > total:
                total = len(g)
        for ci in range(4):
            if len(grids[ci]) < total:
                if grids[ci] and len(grids[ci]) != total:
                    sys.stderr.write('songs2fms: warning: %s channel %d is %d frames, song is %d; padded with rests\n' % (
                        song.name, ci, len(grids[ci]), total))
                grids[ci] = grids[ci] + [0] * (total - len(grids[ci]))
        loop_frame = 0
        decided = False
        for ci, loop_at in enumerate(loops):
            if song.ch[ci] is None:
                continue
            if not decided:
                loop_frame = loop_at
                decided = True
                continue
            if loop_at != loop_frame:
                sys.stderr.write('songs2fms: warning: %s channels disagree on the loop; using channel %d\n' % (
                    song.name, loops.index(loop_frame) if loop_frame in loops else 0))
                break
        marks = [total]
        if isinstance(loop_frame, int) and loop_frame > 0:
            marks.append(loop_frame)
        for grid in grids:
            prev = 0
            for i, tok in enumerate(grid):
                if tok != grid[prev]:
                    marks.append(i)
                    prev = i
        step = choose_step(total, marks)
        ranges, loop_col = split_song(total, step, loop_frame)
        if len(ranges) > 256:
            sys.stderr.write('songs2fms: warning: %s has %d patterns; FamiStudio keeps 256\n' % (song.name, len(ranges)))
            ranges = ranges[:256]
        q = txt2mus.quarter_frames(song.tempo)
        beat = q // step if step and q % step == 0 else 4
        first_notes = (ranges[0][1] - ranges[0][0]) // step if ranges else 1
        if first_notes < 1:
            first_notes = 1
        if beat > first_notes:
            beat = first_notes
        block = []
        block.append('\tSong Name="%s" Length="%d" LoopPoint="%d" PatternLength="%d" BeatLength="%d" NoteLength="%d" Groove="%d" GroovePaddingMode="Middle"' % (
            song.name, len(ranges), loop_col, first_notes, beat, step, step))
        for col, (a, b) in enumerate(ranges):
            notes = (b - a) // step
            if notes != first_notes:
                block.append('\t\tPatternCustomSettings Time="%d" Length="%d" NoteLength="%d" Groove="%d" GroovePaddingMode="Middle" BeatLength="%d"' % (
                    col, notes, step, step, min(beat, notes) if notes else 1))
        for ci in range(4):
            inst = instrument_name(ci, duties[ci], vols[ci])
            if inst not in seen_inst:
                seen_inst.add(inst)
                inst_lines.append('\tInstrument Name="%s"' % inst)
                env_vol = vols[ci]
                inst_lines.append('\t\tEnvelope Type="Volume" Length="1" Values="%d"' % env_vol)
                if ci != 2:
                    duty = duties[ci] & (1 if ci == 3 else 3)
                    inst_lines.append('\t\tEnvelope Type="DutyCycle" Length="1" Values="%d"' % duty)
            block.append('\t\tChannel Type="%s"' % CHANS[ci])
            for col, (a, b) in enumerate(ranges):
                # Skip a silent column; an empty pattern instance is silence anyway.
                if not any(pitch_name(tok, ci == 3) for tok in grids[ci][a:b]):
                    continue
                pname = '%s_%d' % (song.name, col)
                block.append('\t\t\tPattern Name="%s"' % pname)
                emit_notes(block, grids[ci], a, b, inst, ci == 3)
            for col, (a, b) in enumerate(ranges):
                if not any(pitch_name(tok, ci == 3) for tok in grids[ci][a:b]):
                    continue
                pname = '%s_%d' % (song.name, col)
                block.append('\t\t\tPatternInstance Time="%d" Pattern="%s"' % (col, pname))
        song_blocks.append('\n'.join(block))
    lines.extend(inst_lines)
    lines.extend(song_blocks)
    return '\n'.join(lines) + '\n'


def main():
    if len(sys.argv) != 3:
        sys.exit('usage: songs2fms.py <songs.txt> <out.fms.txt>')
    src, dst = sys.argv[1], sys.argv[2]
    songs = txt2mus.parse(src)
    title = os.path.splitext(os.path.basename(src))[0]
    parent = os.path.basename(os.path.dirname(os.path.abspath(src)))
    if parent and parent != 'games':
        title = parent
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    open(dst, 'w').write(export(songs, title))
    print('songs2fms -> %s (%d songs)' % (dst, len(songs)))


if __name__ == '__main__':
    main()
