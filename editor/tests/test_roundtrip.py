#!/usr/bin/env python3
"""File round-trips that do not need a window."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'editor'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.chdir(ROOT)

import re_data
import re_synth
import re_build
import map2c
import txt2mus

BREAKOUT_PAL = [
    0x0F, 0x16, 0x26, 0x06, 0x0F, 0x27, 0x37, 0x17, 0x0F, 0x2A, 0x3A, 0x1A, 0x0F, 0x10, 0x00, 0x30,
    0x0F, 0x30, 0x30, 0x10, 0x0F, 0x21, 0x31, 0x11, 0x0F, 0x30, 0x30, 0x30, 0x0F, 0x30, 0x30, 0x30]
PLATFORMER_PAL = [
    0x21, 0x1A, 0x2A, 0x0A, 0x21, 0x07, 0x17, 0x2A, 0x21, 0x00, 0x10, 0x30, 0x21, 0x30, 0x30, 0x30,
    0x21, 0x16, 0x27, 0x37, 0x21, 0x18, 0x28, 0x38, 0x21, 0x0F, 0x16, 0x30, 0x21, 0x30, 0x30, 0x30]


def map2c_text(path, name):
    return subprocess.check_output([sys.executable, 'tools/map2c.py', path, name], text=True)


def body(text):
    lines = text.splitlines()
    if lines and lines[0].startswith('/*'):
        lines = lines[1:]
    return '\n'.join(lines)


class RoundTrip(unittest.TestCase):
    def test_palettes_match_the_old_tables(self):
        self.assertEqual(re_data.load_palette('games/breakout/palette.txt'), BREAKOUT_PAL)
        self.assertEqual(re_data.load_palette('games/platformer/palette.txt'), PLATFORMER_PAL)

    def test_palette_file_roundtrip(self):
        fd, path = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            re_data.save_palette(path, BREAKOUT_PAL)
            self.assertEqual(re_data.load_palette(path), BREAKOUT_PAL)
        finally:
            os.remove(path)

    def test_tiles_roundtrip(self):
        tiles = re_data.load_tiles('games/breakout/tiles.png')
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        try:
            tiles.tile_set(0x82, 0, 0, 3)
            re_data.save_tiles(path, tiles)
            again = re_data.load_tiles(path)
            self.assertEqual(bytes(again.pixels), bytes(tiles.pixels))
        finally:
            os.remove(path)

    def test_map2c_matches_golden(self):
        for src, name, golden in (
            ('games/breakout/play.txt', 'play', 'editor/tests/golden/play.c'),
            ('games/platformer/level.txt', 'level', 'editor/tests/golden/level.c'),
        ):
            got = map2c_text(src, name)
            self.assertEqual(got, open(golden).read())

    def test_editor_map_emit_matches_map2c(self):
        for path, name in (('games/breakout/play.txt', 'play'), ('games/platformer/level.txt', 'level')):
            gm = re_data.load_map(path)
            fd, tmp = tempfile.mkstemp(suffix='.txt')
            os.close(fd)
            try:
                open(tmp, 'w').write(gm.emit())
                self.assertEqual(body(map2c_text(path, name)), body(map2c_text(tmp, name)))
            finally:
                os.remove(tmp)

    def test_attribute_helper_matches_map2c(self):
        tiles, pal, _solid, _pm = map2c.load('games/platformer/level.txt')
        h, w = len(tiles), len(tiles[0])
        attrs = re_data.attribute_bytes(w, h, lambda x, y: pal.get(tiles[y][x], 0))
        text = map2c_text('games/platformer/level.txt', 'level')
        line = [ln for ln in text.splitlines() if ln.startswith('const unsigned char map_level_attr')][0]
        nums = [int(n) for n in line.split('{', 1)[1].split('}')[0].split(',') if n]
        self.assertEqual(attrs, nums)

    def test_paint_fills_the_attribute_block(self):
        gm = re_data.load_map('games/breakout/play.txt')
        gm.paint(4, 4, 0x82, 1, True)
        for dy in (0, 1):
            for dx in (0, 1):
                self.assertEqual(gm.effective_pal(4 + dx, 4 + dy), 1)
        self.assertEqual(gm.tile_at(4, 4), 0x82)
        self.assertNotEqual(gm.tile_at(5, 4), 0x82)
        fd, tmp = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            open(tmp, 'w').write(gm.emit())
            tiles, _pal, _s, palmap = map2c.load(tmp)
            self.assertIsNotNone(palmap)
            self.assertEqual(palmap[4][4], 1)
            self.assertEqual(tiles[4][4], 0x82)
        finally:
            os.remove(tmp)

    def test_uniform_palmap_matches_legend(self):
        gm = re_data.load_map('games/breakout/play.txt')
        gm.override = [[gm.effective_pal(x, y) for x in range(gm.w)] for y in range(gm.h)]
        fd, tmp = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            open(tmp, 'w').write(gm.emit())
            self.assertEqual(body(map2c_text('games/breakout/play.txt', 'play')), body(map2c_text(tmp, 'play')))
        finally:
            os.remove(tmp)

    def test_songs_emit_matches_compiler(self):
        for game in ('breakout', 'platformer'):
            path = 'games/%s/songs.txt' % game
            songs = re_data.parse_songs(open(path).read())
            fd, tmp = tempfile.mkstemp(suffix='.txt')
            os.close(fd)
            try:
                open(tmp, 'w').write(re_data.emit_songs(songs))
                old, new = txt2mus.parse(path), txt2mus.parse(tmp)
                self.assertEqual(len(old), len(new))
                for a, b in zip(old, new):
                    self.assertEqual(a.name, b.name)
                    self.assertEqual(a.tempo, b.tempo)
                    for ca, cb in zip(a.ch, b.ch):
                        if ca is None or not ca.events:
                            self.assertTrue(cb is None or not cb.events)
                            continue
                        self.assertEqual(ca.events, cb.events)
                        self.assertEqual(ca.vol, cb.vol)
                        self.assertEqual(ca.duty & 1, cb.duty & 1)
                        self.assertEqual(ca.loop_at, cb.loop_at)
            finally:
                os.remove(tmp)

    def test_save_does_not_touch_clean_files(self):
        project = re_data.Project('games/breakout')
        songs = open(project.songs_path).read()
        play = open(project.maps[0].path).read()
        project.save()
        self.assertEqual(open(project.songs_path).read(), songs)
        self.assertEqual(open(project.maps[0].path).read(), play)

    def test_blank_and_copy_project(self):
        folder = tempfile.mkdtemp()
        try:
            blank = re_data.create_project(folder, 'blank', None)
            project = re_data.Project(blank)
            self.assertEqual(len(project.palette), 32)
            self.assertEqual(project.maps[0].name, 'level')
            self.assertTrue(project.songs)
            copied = re_data.create_project(folder, 'copied', os.path.join(ROOT, 'games', 'breakout'))
            again = re_data.Project(copied)
            self.assertEqual(again.palette, BREAKOUT_PAL)
        finally:
            shutil.rmtree(folder)

    def test_synth_c4(self):
        song = re_data.Song('tone')
        song.tempo = 120
        ch = re_data.Channel()
        ch.events = [('C4', 't60')]
        song.ch[0] = ch
        samples = re_synth.render_song(re_data.song_frames(song), seconds=1)
        self.assertGreater(int(abs(samples).max()), 1000)
        # Rising edges of a 50% pulse. C4 is 1789773 / (16 * 428) Hz.
        crossings = 0
        prev = 0
        for value in samples[:re_synth.SR]:
            if prev <= 0 < int(value):
                crossings += 1
            prev = int(value)
        self.assertAlmostEqual(crossings, 261.6, delta=2)

    def test_sfx_is_audible(self):
        samples = re_synth.render_sfx(1)
        self.assertGreater(len(samples), 1000)
        self.assertGreater(int(abs(samples).max()), 1000)

    def test_missing_tool_hint(self):
        tips = re_build.hints_for('pc: sdl2-config not found (install libsdl2-dev)')
        self.assertTrue(any('libsdl2-dev' in tip for tip in tips))


if __name__ == '__main__':
    unittest.main()
