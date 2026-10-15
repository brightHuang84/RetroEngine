#!/usr/bin/env python3
"""Import FamiStudio text (File > Export > FamiStudio Text) into songs.txt.

  python3 tools/fms2mus.py --out build/<game>/gen/songs.gen.txt \\
      games/<game>/songs.txt games/<game>/music/*.fms.txt

Files that are already songs.txt are copied through. FamiStudio text is
flattened to frame-accurate `tN` durations so txt2mus.py can compile it.
Square1/2, Triangle and Noise become pulse1/2, triangle and noise.
Anything the engine cannot play is warned about and skipped, not fatal.

Timing: FamiStudio tempo stores note Time and Duration in frames when the
groove is a single value (the usual case). A swing groove (two sizes) is
expanded with the same pad rule the player uses. FamiTracker tempo uses the
NTSC tick counter (tempo 150, speed N -> N frames per row). A single event
is at most 255 frames; longer notes are split into back-to-back copies of
the same pitch, which does not retrigger the waveform.
"""
import os
import re
import sys

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
CHANS = {
    'Square1': 0, 'Square2': 1, 'Triangle': 2, 'Noise': 3,
}
PAD = {'Beginning': 0, 'Middle': 1, 'End': 2}
ATTR = re.compile(r'([A-Za-z0-9_]+)\s*=\s*"((?:""|[^"])*)"')
KIND = re.compile(r'([A-Za-z0-9_]+)\b\s*(.*)$')
DROPPED_EFFECTS = (
    'SlideTarget', 'Arpeggio', 'VibratoSpeed', 'VibratoDepth', 'FinePitch',
    'VolumeSlideTarget', 'FdsModSpeed', 'FdsModDepth', 'PhaseReset',
    'EnvelopePeriod', 'DeltaCounter',
)


class Warn(object):
    def __init__(self, path):
        self.path = path
        self.seen = set()

    def say(self, key, msg):
        if key in self.seen:
            return
        self.seen.add(key)
        sys.stderr.write('fms2mus: warning: %s: %s\n' % (self.path, msg))


def parse_line(line):
    raw = line.strip()
    if not raw or raw.startswith('#') or raw.startswith('//'):
        return None, {}
    m = KIND.match(raw)
    if not m:
        return None, {}
    attrs = {}
    for k, v in ATTR.findall(m.group(2)):
        attrs[k] = v.replace('""', '"')
    return m.group(1), attrs


def friendly_to_value(name):
    if name in ('', 'Stop', 'Release'):
        return name
    if len(name) < 2 or not name[-1].isdigit():
        raise ValueError(name)
    note = name[:-1]
    # Accept a trailing flat (Bb4) even though FamiStudio writes sharps.
    acc = 0
    if note.endswith('b') and len(note) == 2:
        note = note[0]
        acc = -1
    if note not in NOTE_NAMES:
        raise ValueError(name)
    octave = int(name[-1])
    return octave * 12 + NOTE_NAMES.index(note) + 1 + acc


def engine_pitch(fs_value, noise):
    """Return a songs.txt token, or None if this value is a rest/stop."""
    if fs_value in ('Stop', 'Release', '', None):
        return None
    if noise:
        period = int(fs_value) - 1
        if period < 0 or period > 15:
            period = max(0, min(15, period))
        return 'N%d' % period
    idx = int(fs_value) - 12  # FamiStudio C0 == 1, engine C1 == 1
    if idx < 1:
        idx = 1
    if idx > 84:
        idx = 84
    idx -= 1
    return NOTE_NAMES[idx % 12] + str(idx // 12 + 1)


class Groove(object):
    def __init__(self, groove, pad_name):
        self.g = list(groove) or [1]
        self.pad = PAD.get(pad_name, 1)
        self.nl = min(self.g)
        self.gfi = 0
        self.gai = 0

    def is_pad(self):
        if self.g[self.gai] == self.nl:
            return False
        if self.pad == 0 and self.gfi == 0:
            return True
        if self.pad == 1 and self.gfi == (self.nl // 2):
            return True
        if self.pad == 2 and self.gfi == self.nl:
            return True
        return False

    def advance(self):
        self.gfi += 1
        if self.gfi == self.g[self.gai]:
            self.gfi = 0
            self.gai = (self.gai + 1) % len(self.g)


def pattern_clock(length, groove, pad_name):
    """Map each note-index to the NTSC frame it starts on. Uniform grooves
    are the identity: index i is heard on frame i, and the pattern lasts
    `length` frames."""
    it = Groove(groove, pad_name)
    starts = []
    total = 0
    note = 0
    valid = False
    guard = 0
    limit = max(length, 1) * (max(groove) + 2) + 4
    while guard < limit:
        guard += 1
        if not valid:
            valid = True
            starts.append(0)
            it.advance()
            total = 1
            continue
        if not it.is_pad():
            note += 1
            if note >= length:
                break
            starts.append(total)
        it.advance()
        total += 1
    if len(starts) < length:
        # Fall back to 1:1 if the groove never finishes (should not happen).
        starts = list(range(length))
        total = length
    return starts, total


def ft_row_frames(n_rows, tempo, speed, speed_at):
    """NTSC frames per row, matching FamiStudio's FamiTracker tempo counter."""
    counter = 0
    spd = speed if speed > 0 else 1
    lengths = [0] * n_rows
    row = -1
    guard = 0
    while guard < n_rows * 4000 + 10:
        guard += 1
        if counter <= 0:
            row += 1
            if row >= n_rows:
                break
            if row in speed_at:
                spd = speed_at[row] if speed_at[row] > 0 else 1
        lengths[row] += 1
        dec = (tempo * 24) // spd
        rem = (tempo * 24) % spd
        if dec < 1:
            dec = 1
        if counter <= 0:
            counter += (60 * 60) - rem
        counter -= dec
    return lengths


def _groove_values(text, warn, name):
    out = []
    for part in text.split('-'):
        part = part.strip()
        if not part:
            continue
        try:
            g = int(part)
        except ValueError:
            warn.say('groove-bad-' + name, 'song %s has a bad groove; using 6' % name)
            return [6]
        if g < 1 or g > 18:
            warn.say('groove-range', 'groove value %d is outside 1..18; clamped' % g)
            if g < 1:
                g = 1
            if g > 18:
                g = 18
        out.append(g)
    return out or [6]


def most_common(vals, default):
    if not vals:
        return default
    count = {}
    best = vals[0]
    best_n = 0
    for v in vals:
        count[v] = count.get(v, 0) + 1
        if count[v] > best_n:
            best_n = count[v]
            best = v
    return best


def song_ident(name, used):
    raw = name.strip().lower()
    chars = []
    for c in raw:
        chars.append(c if c.isalnum() else '_')
    ident = ''.join(chars).strip('_')
    while '__' in ident:
        ident = ident.replace('__', '_')
    if not ident or ident[0].isdigit():
        ident = 's_' + ident
    base = ident
    n = 2
    while ident in used:
        ident = '%s_%d' % (base, n)
        n += 1
    used.add(ident)
    return ident


def compress(grid):
    events = []
    i = 0
    n = len(grid)
    while i < n:
        tok = grid[i]
        j = i + 1
        while j < n and grid[j] == tok:
            j += 1
        dur = j - i
        while dur > 255:
            events.append((tok, 255))
            dur -= 255
        if dur > 0:
            events.append((tok, dur))
        i = j
    return events


def split_at(events, cut):
    intro = []
    loop = []
    t = 0
    for tok, dur in events:
        left = dur
        while left:
            if cut is not None and t < cut:
                take = left if t + left <= cut else cut - t
                intro.append((tok, take))
                t += take
                left -= take
            else:
                loop.append((tok, left))
                t += left
                left = 0
    return _merge(intro), _merge(loop)


def _merge(events):
    out = []
    for tok, dur in events:
        if dur < 1:
            continue
        if out and out[-1][0] == tok and out[-1][1] + dur <= 255:
            out[-1] = (tok, out[-1][1] + dur)
        else:
            while dur > 255:
                out.append((tok, 255))
                dur -= 255
            if dur:
                out.append((tok, dur))
    return out


def has_sound(events):
    for tok, _dur in events:
        if tok != 'R':
            return True
    return False


class Inst(object):
    def __init__(self):
        self.vol = 10
        self.duty = 2
        self.vol_env = False


def load_fms(path, warn):
    instruments = {}
    cur_inst = None
    songs = []
    song = None
    chan = None
    pattern = None
    saw_project = False
    for line_no, line in enumerate(open(path), 1):
        kind, attrs = parse_line(line)
        if kind is None:
            if line.strip() and not line.strip().startswith('#'):
                warn.say('bad-line', 'unparsed line %d' % line_no)
            continue
        if kind == 'Project':
            saw_project = True
            if attrs.get('PAL', '').lower() == 'true':
                warn.say('pal', 'PAL project is timed as NTSC 60 Hz, so it will run fast')
            if 'Tuning' in attrs and attrs['Tuning'] not in ('440', ''):
                warn.say('tuning', 'tuning %s Hz is ignored; pitches stay at A440' % attrs['Tuning'])
            exp = attrs.get('Expansions', '')
            if exp:
                warn.say('exp', 'expansion chips (%s) are not imported' % exp)
            continue
        if kind == 'DPCMSample':
            warn.say('dpcm', 'DPCM samples are not imported')
            continue
        if kind == 'DPCMMapping':
            warn.say('dpcm', 'DPCM samples are not imported')
            continue
        if kind == 'Arpeggio':
            warn.say('arp', 'arpeggios are ignored')
            continue
        if kind == 'Instrument':
            cur_inst = Inst()
            instruments[attrs.get('Name', '')] = cur_inst
            exp = attrs.get('Expansion', '')
            if exp:
                warn.say('inst-exp-' + exp, 'instrument expansion %s is ignored' % exp)
            continue
        if kind == 'Envelope':
            if cur_inst is None:
                continue
            et = attrs.get('Type', '')
            vals = []
            for part in attrs.get('Values', '').split(','):
                part = part.strip()
                if part:
                    try:
                        vals.append(int(part))
                    except ValueError:
                        warn.say('env-val', 'bad envelope value')
            if et == 'Volume' and vals:
                cur_inst.vol = max(0, min(15, max(vals)))
                if len(vals) > 1 or 'Release' in attrs or 'Loop' in attrs:
                    cur_inst.vol_env = True
            elif et == 'DutyCycle' and vals:
                cur_inst.duty = max(0, min(3, vals[0]))
            elif et in ('Arpeggio', 'Pitch'):
                warn.say('env-' + et, '%s envelopes are ignored' % et)
            continue
        if kind == 'Song':
            song = {
                'name': attrs.get('Name', 'song'),
                'length': int(attrs.get('Length', '1') or '1'),
                'loop': int(attrs.get('LoopPoint', '0') or '0'),
                'pat_notes': int(attrs.get('PatternLength', '16') or '16'),
                'note_len': int(attrs.get('NoteLength', '0') or '0'),
                'ft_tempo': int(attrs.get('FamiTrackerTempo', '0') or '0'),
                'ft_speed': int(attrs.get('FamiTrackerSpeed', '6') or '6'),
                'groove': None,
                'pad': attrs.get('GroovePaddingMode', 'Middle'),
                'custom': {},
                'channels': {},
            }
            g = attrs.get('Groove', '')
            if g:
                song['groove'] = _groove_values(g, warn, song['name'])
            elif song['note_len'] > 0:
                song['groove'] = _groove_values(str(song['note_len']), warn, song['name'])
            if song['ft_tempo'] <= 0 and not song['groove']:
                song['groove'] = [6]
                song['note_len'] = 6
                warn.say('tempo', 'song %s has no tempo; using 6 frames per row' % song['name'])
            songs.append(song)
            chan = None
            pattern = None
            continue
        if song is None:
            continue
        if kind == 'PatternCustomSettings':
            col = int(attrs.get('Time', '0') or '0')
            song['custom'][col] = attrs
            continue
        if kind == 'Channel':
            ctype = attrs.get('Type', '')
            if ctype not in CHANS:
                warn.say('ch-' + ctype, 'channel %s is not imported' % ctype)
                chan = None
                pattern = None
                continue
            chan = {'type': ctype, 'patterns': {}, 'instances': {}}
            song['channels'][CHANS[ctype]] = chan
            pattern = None
            continue
        if chan is None:
            continue
        if kind == 'Pattern':
            pattern = {'name': attrs.get('Name', ''), 'notes': []}
            chan['patterns'][pattern['name']] = pattern
            continue
        if kind == 'Note':
            if pattern is None:
                continue
            pattern['notes'].append(attrs)
            continue
        if kind == 'PatternInstance':
            chan['instances'][int(attrs.get('Time', '0') or '0')] = attrs.get('Pattern', '')
            continue
    if not saw_project:
        raise ValueError('not a FamiStudio text file (no Project line)')
    return instruments, songs


def column_spec(song, index, warn):
    custom = song['custom'].get(index, {})
    if song['ft_tempo'] > 0:
        rows = int(custom.get('Length', song['pat_notes']) or song['pat_notes'])
        return {'ft': True, 'rows': rows}
    notes = int(custom.get('Length', song['pat_notes']) or song['pat_notes'])
    if 'Groove' in custom:
        groove = _groove_values(custom['Groove'], warn, song['name'])
    else:
        groove = list(song['groove'])
    pad = custom.get('GroovePaddingMode', song['pad'])
    note_len = int(custom.get('NoteLength', song['note_len'] or min(groove)) or min(groove))
    if min(groove) != note_len:
        warn.say('groove', 'NoteLength %d does not match groove %s; using the groove' % (note_len, groove))
    length = notes * min(groove)
    starts, total = pattern_clock(length, groove, pad)
    if any(g != groove[0] for g in groove):
        warn.say('swing', 'swing groove %s is expanded to frames; volume and pitch effects inside a row are not' % '-'.join(str(g) for g in groove))
    return {'ft': False, 'length': length, 'starts': starts, 'total': total}


def paint_song(song, instruments, warn):
    specs = [column_spec(song, i, warn) for i in range(song['length'])]
    # Frame length of each column, and a map from (column, local-time) to a frame span.
    col_frames = []
    for spec in specs:
        if spec['ft']:
            col_frames.append(None)  # filled after speed effects are known
        else:
            col_frames.append(spec['total'])

    channels_out = []
    for ci in range(4):
        chan = song['channels'].get(ci)
        # Collect speed changes (FT) across channels first; do it outside.
        channels_out.append(chan)
    speed_at = {}
    if song['ft_tempo'] > 0:
        base_rows = []
        acc = 0
        for spec in specs:
            base_rows.append(acc)
            acc += spec['rows']
        for chan in channels_out:
            if not chan:
                continue
            for col, pname in chan['instances'].items():
                if col < 0 or col >= song['length']:
                    continue
                pat = chan['patterns'].get(pname)
                if not pat:
                    continue
                for note in pat['notes']:
                    if 'Speed' not in note:
                        continue
                    local = int(note.get('Time', '0') or '0')
                    speed_at[base_rows[col] + local] = int(note['Speed'])
        all_rows = sum(spec['rows'] for spec in specs)
        flat = ft_row_frames(all_rows, song['ft_tempo'], song['ft_speed'], speed_at)
        # Split flat back into columns.
        pos = 0
        for i, spec in enumerate(specs):
            chunk = flat[pos:pos + spec['rows']]
            spec['row_frames'] = chunk
            spec['cum'] = []
            t = 0
            for fr in chunk:
                spec['cum'].append(t)
                t += fr
            spec['total'] = t
            col_frames[i] = t
            pos += spec['rows']
        if speed_at:
            warn.say('speed', 'FamiTracker speed changes are applied to row timing')

    offsets = []
    acc = 0
    for n in col_frames:
        offsets.append(acc)
        acc += n if n else 0
    total = acc
    loop_at = song['loop']
    if loop_at < 0:
        cut = None  # play once
    elif loop_at == 0 or loop_at >= song['length']:
        if loop_at >= song['length'] and loop_at != 0:
            warn.say('loop', 'loop point %d is past the song; looping from the start' % loop_at)
        cut = 0
    else:
        cut = offsets[loop_at]

    rendered = []
    for ci in range(4):
        chan = song['channels'].get(ci)
        grid = ['R'] * total
        vols = []
        duties = []
        if chan:
            for col, pname in sorted(chan['instances'].items()):
                if col < 0 or col >= song['length']:
                    continue
                pat = chan['patterns'].get(pname)
                if pat is None:
                    warn.say('missing-pat', 'missing pattern %s' % pname)
                    continue
                spec = specs[col]
                base = offsets[col]
                notes = sorted(pat['notes'], key=lambda n: int(n.get('Time', '0') or '0'))
                # Musical notes first, then stops cut them.
                for note in notes:
                    _warn_effects(note, warn, song['ft_tempo'] > 0)
                    if 'Value' not in note:
                        continue
                    try:
                        raw = friendly_to_value(note['Value'])
                    except ValueError:
                        warn.say('bad-note', 'bad note %s' % note.get('Value'))
                        continue
                    if raw in ('Stop', 'Release'):
                        continue
                    if ci == 3 and not (1 <= raw <= 16):
                        warn.say('noise-range', 'noise note %s is outside C0..D#1; clamped to N0..N15' % note['Value'])
                    elif ci != 3 and (raw < 13 or raw > 96):
                        warn.say('pitch-range', 'note %s is outside C1..B7; clamped' % note['Value'])
                    tok = engine_pitch(raw, ci == 3)
                    t0 = int(note.get('Time', '0') or '0')
                    dur = int(note.get('Duration', '1') or '1')
                    delay = int(note.get('NoteDelay', '0') or '0') if 'NoteDelay' in note else 0
                    cutd = int(note.get('CutDelay', '0') or '0') if 'CutDelay' in note else 0
                    if 'NoteDelay' in note or 'CutDelay' in note:
                        warn.say('delay', 'NoteDelay and CutDelay are applied as frame offsets')
                    inst = instruments.get(note.get('Instrument', ''))
                    vol = inst.vol if inst else 10
                    duty = inst.duty if inst else 2
                    if inst and inst.vol_env:
                        warn.say('env-vol', 'volume envelopes are reduced to their peak value')
                    if 'Volume' in note:
                        vol = max(0, min(15, int(note['Volume'])))
                    if 'DutyCycle' in note:
                        duty = max(0, min(3, int(note['DutyCycle'])))
                    vols.append(vol)
                    duties.append(duty)
                    a, b = _span(spec, t0, dur)
                    if a is None:
                        warn.say('past-end', 'a note starts past the end of a pattern and was dropped')
                        continue
                    if 'Release' in note:
                        warn.say('release', 'release points are treated as stops; the release envelope is not played')
                        rel = int(note.get('Release') or '0')
                        _ra, rb = _span(spec, t0, rel)
                        if rb is not None and rb < b:
                            b = rb
                    a += delay
                    if cutd > 0:
                        b = min(b, _span(spec, t0, 0)[0] + cutd)
                    if a >= b:
                        continue
                    for f in range(base + a, min(base + b, total)):
                        grid[f] = tok
                for note in notes:
                    if note.get('Value') not in ('Stop', 'Release'):
                        continue
                    if note.get('Value') == 'Release':
                        warn.say('release', 'release points are treated as stops; the release envelope is not played')
                    t0 = int(note.get('Time', '0') or '0')
                    a, _b = _span(spec, t0, 1)
                    if a is None:
                        continue
                    # Notes were painted first. Blank from this stop up to the next
                    # musical note, which keeps that later note.
                    end = spec['total']
                    for later in notes:
                        lt = int(later.get('Time', '0') or '0')
                        if lt <= t0 or 'Value' not in later or later['Value'] in ('Stop', 'Release'):
                            continue
                        end_at = _span(spec, lt, 1)[0]
                        if end_at is not None:
                            end = end_at
                        break
                    for f in range(base + a, min(base + end, total)):
                        grid[f] = 'R'
        vol = most_common(vols, 10)
        duty = most_common(duties, 2 if ci < 2 else 0)
        if len(set(vols)) > 1:
            warn.say('vol-mix-%d' % ci, 'channel %d uses more than one volume; keeping %d' % (ci, vol))
        if ci != 2 and len(set(duties)) > 1:
            kept = duty & (1 if ci == 3 else 3)
            warn.say('duty-mix-%d' % ci, 'channel %d uses more than one duty; keeping %d' % (ci, kept))
        rendered.append({'grid': grid, 'vol': vol, 'duty': duty & (1 if ci == 3 else 3)})
    return rendered, total, cut


def _span(spec, t0, dur):
    if spec['ft']:
        cum = spec['cum']
        if t0 < 0 or t0 >= len(cum):
            return None, None
        a = cum[t0]
        end_row = t0 + max(dur, 0)
        if end_row >= len(cum):
            b = spec['total']
        else:
            b = cum[end_row]
        if dur <= 0:
            b = a
        return a, b
    starts = spec['starts']
    if t0 < 0 or t0 >= len(starts):
        return None, None
    a = starts[t0]
    end_i = t0 + max(dur, 0)
    if end_i >= len(starts):
        b = spec['total']
    else:
        b = starts[end_i]
    if dur <= 0:
        b = a
    return a, b


def _warn_effects(note, warn, ft):
    for name in DROPPED_EFFECTS:
        if name in note:
            warn.say('fx-' + name, '%s is ignored' % name)
    if note.get('Attack', 'True') == 'False':
        warn.say('attack', 'notes without an attack still change pitch immediately')
    if 'Speed' in note and not ft:
        warn.say('speed-fs', 'Speed effects are ignored in FamiStudio tempo mode')
    if 'Arpeggio' in note:
        warn.say('arp', 'arpeggios are ignored')


def emit_song(ident, original, rendered, cut, lines):
    lines.append('# imported from FamiStudio song "%s"' % original)
    lines.append('song %s' % ident)
    lines.append('tempo 120')
    cnames = ['pulse1', 'pulse2', 'triangle', 'noise']
    once = cut is None
    for ci, ch in enumerate(rendered):
        events = compress(ch['grid'])
        if not has_sound(events):
            continue
        if ci == 3:
            head = 'noise vol %d mode %d' % (ch['vol'], ch['duty'] & 1)
        elif ci == 2:
            head = 'triangle vol %d' % ch['vol']
        else:
            head = '%s duty %d vol %d' % (cnames[ci], ch['duty'] & 3, ch['vol'])
        if once:
            head += ' once'
        lines.append(head)
        intro, loop = split_at(events, 0 if cut is None else cut)
        body = intro if once else intro
        if once:
            body = _merge(intro + loop)
            _write_events(lines, body)
        else:
            if cut and intro:
                _write_events(lines, intro)
                lines.append('  loop')
                _write_events(lines, loop)
            else:
                _write_events(lines, loop if loop else intro)
    lines.append('')


def _write_events(lines, events):
    bits = []
    for tok, dur in events:
        bits.append('%s t%d' % (tok, dur))
    for i in range(0, len(bits), 8):
        lines.append('  ' + ' '.join(bits[i:i + 8]))


def convert_fms(path, used):
    warn = Warn(os.path.basename(path))
    instruments, songs = load_fms(path, warn)
    chunks = []
    for song in songs:
        rendered, _total, cut = paint_song(song, instruments, warn)
        ident = song_ident(song['name'], used)
        if ident != _slug(song['name']):
            warn.say('rename-' + ident, 'song "%s" imported as %s' % (song['name'], ident))
        lines = []
        emit_song(ident, song['name'], rendered, cut, lines)
        chunks.append('\n'.join(lines).rstrip() + '\n')
    return ''.join(chunks)


def _slug(name):
    chars = []
    for c in name.strip().lower():
        chars.append(c if c.isalnum() else '_')
    ident = ''.join(chars).strip('_')
    while '__' in ident:
        ident = ident.replace('__', '_')
    if not ident or ident[0].isdigit():
        ident = 's_' + ident
    return ident


def is_fms(path):
    for line in open(path):
        kind, _attrs = parse_line(line)
        if kind == 'Project':
            return True
        if kind == 'song':
            return False
    return False


def main():
    args = sys.argv[1:]
    out = None
    files = []
    i = 0
    while i < len(args):
        if args[i] == '--out':
            out = args[i + 1]
            i += 2
            continue
        files.append(args[i])
        i += 1
    if not out or not files:
        sys.exit('usage: fms2mus.py --out songs.gen.txt <songs.txt or .fms.txt>...')
    used = set()
    parts = []
    for path in files:
        if is_fms(path):
            # Names already taken by earlier files stay unique.
            text = convert_fms(path, used)
            # convert_fms adds idents to `used` via song_ident. Songs.txt
            # names are registered below when we copy a songs file.
            parts.append(text)
        else:
            body = open(path).read()
            if body and not body.endswith('\n'):
                body += '\n'
            parts.append(body)
            for line in body.splitlines():
                bits = line.split()
                if bits and bits[0] == 'song' and len(bits) >= 2:
                    used.add(bits[1])
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'w').write(''.join(parts))
    print('fms2mus -> %s' % out)


if __name__ == '__main__':
    main()
