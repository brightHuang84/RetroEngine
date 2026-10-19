"""NES-style mixer matching platform/sdl/main_sdl.c and engine/engine.c.

One engine frame is 735 samples at 44100 Hz. Pulse and noise use the same
duty sequences, timers and LFSR as the SDL backend. Triangle uses the
halved period the engine writes for that channel.
"""
import array

import numpy as np

SR = 44100
FRAME = 735
CYC_Q16 = (1789773 << 16) // 44100
DUTY_SEQ = (0x02, 0x06, 0x1E, 0xF9)
NOISE_TIMER = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068)
NOTE_PERIOD = (
    0,
    3419, 3228, 3046, 2875, 2714, 2561, 2418, 2282, 2154, 2033, 1919, 1811,
    1709, 1613, 1523, 1437, 1356, 1280, 1208, 1140, 1076, 1016, 959, 905,
    854, 806, 761, 718, 678, 640, 604, 570, 538, 507, 479, 452,
    427, 403, 380, 359, 338, 319, 301, 284, 268, 253, 239, 225,
    213, 201, 189, 179, 169, 159, 150, 142, 134, 126, 119, 112,
    106, 100, 94, 89, 84, 79, 75, 70, 66, 63, 59, 56,
    52, 49, 47, 44, 41, 39, 37, 35, 33, 31, 29, 27,
)
SFX = (
    (),
    ((0x0FD, 3),),
    ((0x1FC, 2), (0x17C, 3)),
    ((0x0D5, 4), (0x09F, 8)),
    ((0x2A0, 2), (0x1C0, 2), (0x150, 3)),
    ((0x350, 8), (0x470, 8), (0x5F0, 14)),
    ((0x1AB, 6), (0x153, 6), (0x11D, 6), (0x0D5, 16)),
)
SFX_NAMES = ['', 'BLIP', 'HIT', 'COIN', 'JUMP', 'LOSE', 'WIN']


def engine_period(channel, pitch):
    """pitch is the songs.txt index (0 rest, 1..84 notes, noise 1..16)."""
    if pitch <= 0:
        return 0
    if channel == 3:
        return (pitch - 1) & 15
    p = NOTE_PERIOD[pitch if pitch < 85 else 84]
    if channel == 2:
        half = (p + 1) >> 1
        return (half - 1) if half else 0
    if p > 0x7FF:
        p = 0x7FF
    return p


class Mixer(object):
    def __init__(self):
        self.pulse_acc = [0, 0, 0, 0]
        self.pulse_step = [0, 0, 0, 0]
        self.tri_acc = 0
        self.tri_step = 0
        self.noise_acc = 0
        self.lfsr = 1

    def _pulse_bit(self, idx, period, duty):
        if period < 8:
            period = 8
        thr = (2 * (period + 1)) << 16
        self.pulse_acc[idx] += CYC_Q16
        while self.pulse_acc[idx] >= thr:
            self.pulse_acc[idx] -= thr
            self.pulse_step[idx] = (self.pulse_step[idx] + 1) & 7
        return (DUTY_SEQ[duty & 3] >> self.pulse_step[idx]) & 1

    def _tri(self, period):
        if period < 1:
            period = 1
        thr = (period + 1) << 16
        self.tri_acc += CYC_Q16
        while self.tri_acc >= thr:
            self.tri_acc -= thr
            self.tri_step = (self.tri_step + 1) & 31
        v = self.tri_step
        if v < 16:
            return (15 - v) - 8
        return (v - 16) - 8

    def _noise(self, idx, mode):
        if idx > 15:
            idx = 15
        thr = NOISE_TIMER[idx] << 16
        self.noise_acc += CYC_Q16
        while self.noise_acc >= thr:
            self.noise_acc -= thr
            if mode:
                fb = (self.lfsr ^ (self.lfsr >> 6)) & 1
            else:
                fb = (self.lfsr ^ (self.lfsr >> 1)) & 1
            self.lfsr = ((self.lfsr >> 1) | (fb << 14)) & 0x7FFF
            if not self.lfsr:
                self.lfsr = 1
        return 0 if (self.lfsr & 1) else 1

    def mix(self, n, period, vol, duty):
        out = array.array('h')
        for _ in range(n):
            mix = 0
            if vol[0]:
                bit = self._pulse_bit(0, period[0], duty[0])
                mix += (vol[0] if bit else -vol[0]) * 320
            if vol[1]:
                bit = self._pulse_bit(1, period[1], duty[1])
                mix += (vol[1] if bit else -vol[1]) * 320
            if vol[2]:
                mix += self._tri(period[2]) * vol[2] * 22
            if len(vol) > 3 and vol[3]:
                bit = self._noise(period[3], duty[3] & 1)
                mix += (vol[3] if bit else -vol[3]) * 200
            if len(vol) > 4 and vol[4]:
                bit = self._pulse_bit(2, period[4], duty[4])
                mix += (vol[4] if bit else -vol[4]) * 320
            if len(vol) > 5 and vol[5]:
                bit = self._pulse_bit(3, period[5], duty[5])
                mix += (vol[5] if bit else -vol[5]) * 320
            if mix > 32767:
                mix = 32767
            if mix < -32768:
                mix = -32768
            out.append(mix)
        return out


class _Seq(object):
    def __init__(self, channel, events, loop_at, once, duty, vol):
        self.channel = channel
        self.events = events
        self.loop_at = 0 if loop_at is None else loop_at
        self.once = once
        self.duty = duty
        self.vol = vol
        self.index = 0
        self.timer = 0
        self.period = 0
        self.gate = 0
        self.dead = not events

    def step(self):
        if self.dead:
            self.gate = 0
            return
        if self.timer:
            self.timer -= 1
            return
        guard = 0
        while guard < 4:
            guard += 1
            if self.index >= len(self.events):
                if self.once:
                    self.dead = True
                    self.gate = 0
                    return
                self.index = self.loop_at
                if self.index >= len(self.events):
                    self.dead = True
                    self.gate = 0
                    return
            pitch, dur = self.events[self.index]
            self.index += 1
            if dur < 1:
                dur = 1
            if pitch == 0:
                self.gate = 0
                self.period = 0
            else:
                self.gate = 1
                self.period = engine_period(self.channel, pitch)
            self.timer = dur - 1
            return


def render_song(compiled, seconds=4, master=12):
    """compiled is a txt2mus.Song. Returns an array of signed 16-bit samples."""
    seqs = []
    for i, ch in enumerate(compiled.ch):
        if ch is None or not ch.events:
            seqs.append(_Seq(i, [], 0, True, 2, 0))
        else:
            seqs.append(_Seq(i, ch.events, ch.loop_at, ch.once, ch.duty & 3, ch.vol))
    frames = int(seconds * 60)
    mix = Mixer()
    out = array.array('h')
    for _ in range(frames):
        period, vol, duty = [0] * 6, [0] * 6, [2] * 6
        for i, seq in enumerate(seqs):
            seq.step()
            duty[i] = seq.duty
            period[i] = seq.period
            v = seq.vol if seq.gate else 0
            vol[i] = (v * master) // 15
        out.extend(mix.mix(FRAME, period, vol, duty))
    return np.array(out, dtype=np.int16)


def render_sfx(sfx_id):
    """sfx_id matches the engine: 1 BLIP, 2 HIT, 3 COIN, 4 JUMP, 5 LOSE, 6 WIN."""
    events = SFX[sfx_id] if 0 < sfx_id < len(SFX) else ()
    mix = Mixer()
    out = array.array('h')
    ei = 0
    left = 0
    period = 0
    while ei < len(events) or left:
        if left:
            left -= 1
        elif ei < len(events):
            period, dur = events[ei]
            ei += 1
            if dur < 1:
                dur = 1
            left = dur - 1
        out.extend(mix.mix(FRAME, [0, period, 0, 0], [0, 14, 0, 0], [2, 2, 0, 0]))
    return np.array(out, dtype=np.int16)
