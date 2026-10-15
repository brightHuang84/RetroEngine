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
import ent2c
import mappack

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
            ('games/breakout/maps/play.txt', 'play', 'editor/tests/golden/play.c'),
            ('games/platformer/maps/level1.txt', 'level', 'editor/tests/golden/level.c'),
        ):
            got = map2c_text(src, name)
            self.assertEqual(got, open(golden).read())

    def test_editor_map_emit_matches_map2c(self):
        for path, name in (('games/breakout/maps/play.txt', 'play'), ('games/platformer/maps/level1.txt', 'level')):
            gm = re_data.load_map(path)
            fd, tmp = tempfile.mkstemp(suffix='.txt')
            os.close(fd)
            try:
                open(tmp, 'w').write(gm.emit())
                self.assertEqual(body(map2c_text(path, name)), body(map2c_text(tmp, name)))
            finally:
                os.remove(tmp)

    def test_attribute_helper_matches_map2c(self):
        tiles, pal, _solid, _pm = map2c.load('games/platformer/maps/level1.txt')
        h, w = len(tiles), len(tiles[0])
        attrs = re_data.attribute_bytes(w, h, lambda x, y: pal.get(tiles[y][x], 0))
        text = map2c_text('games/platformer/maps/level1.txt', 'level')
        line = [ln for ln in text.splitlines() if ln.startswith('const unsigned char map_level_attr')][0]
        nums = [int(n) for n in line.split('{', 1)[1].split('}')[0].split(',') if n]
        self.assertEqual(attrs, nums)

    def test_paint_fills_the_attribute_block(self):
        gm = re_data.load_map('games/breakout/maps/play.txt')
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
        gm = re_data.load_map('games/breakout/maps/play.txt')
        gm.override = [[gm.effective_pal(x, y) for x in range(gm.w)] for y in range(gm.h)]
        fd, tmp = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        try:
            open(tmp, 'w').write(gm.emit())
            self.assertEqual(body(map2c_text('games/breakout/maps/play.txt', 'play')), body(map2c_text(tmp, 'play')))
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

    def test_entities_roundtrip_and_pack(self):
        for game, expect in (
            ('platformer', [('player', 16, 192), ('coin', 56, 196), ('enemy', 280, 200)]),
            ('breakout', [('paddle', 112, 200), ('ball', 124, 192)]),
        ):
            spec = ent2c.load_types('games/%s/entities.txt' % game)
            self.assertGreater(len(spec.types), 0)
            self.assertLessEqual(spec.limit, ent2c.ENT_ABS_MAX)
            gm = re_data.load_map('games/%s/maps/%s.txt' % (
                game, 'level1' if game == 'platformer' else 'play'))
            by_type = {}
            for ent in gm.entities:
                by_type.setdefault(ent.type, ent)
            for name, x, y in expect:
                self.assertEqual((by_type[name].x, by_type[name].y), (x, y))
            text = gm.emit(spec)
            again = ent2c.entities_from_map_text(text)
            self.assertEqual([(e.type, e.x, e.y, e.props) for e in again],
                             [(e.type, e.x, e.y, dict(spec.by_name(e.type).props, **e.props)) for e in gm.entities])
            for ent in gm.entities:
                self.assertEqual(len(ent2c.pack(ent, spec)), ent2c.ENT_BYTES)
            state = gm.copy_state()
            gm.entities.append(ent2c.Entity('coin' if game == 'platformer' else 'ball', 8, 8, {}))
            gm.restore_state(state)
            self.assertEqual(len(gm.entities), len(again))

    def test_entity_limit_is_an_error(self):
        spec = ent2c.load_types('games/breakout/entities.txt')
        spec.limit = 1
        too_many = [ent2c.Entity('ball', 1, 1, {}), ent2c.Entity('ball', 2, 2, {})]
        with self.assertRaises(SystemExit):
            ent2c.check_count(too_many, spec, 'test')
        with self.assertRaises(SystemExit):
            ent2c.pack(ent2c.Entity('nope', 0, 0, {}), spec)
        with self.assertRaises(SystemExit):
            ent2c.parse_entity_line('ball 1 2 extra')

    def test_generated_tables_match_the_maps(self):
        for game in ('breakout', 'platformer'):
            text = ent2c.emit_game('games/%s' % game)
            self.assertIn('#define ENT_LIMIT', text)
            self.assertIn('_ent[', text)
            self.assertLessEqual(text.count('const unsigned char map_'), 8)

    def test_missing_tool_hint(self):
        tips = re_build.hints_for('pc: sdl2-config not found (install libsdl2-dev)')
        self.assertTrue(any('libsdl2-dev' in tip for tip in tips))
        tips = re_build.hints_for('错误：NES NROM 的 32KB PRG 放不下。')
        self.assertTrue(tips)

    def test_column_rle_roundtrip_and_level_order(self):
        tiles, pal, _solid, palmap = map2c.load('games/platformer/maps/long.txt')
        cols = [[tiles[y][x] for y in range(len(tiles))] for x in range(len(tiles[0]))]
        self.assertEqual(len(cols), 256)
        self.assertEqual(len(tiles), 30)
        for col in cols:
            blob = mappack.rle_encode(col)
            self.assertEqual(mappack.rle_decode(blob, 30), col)
        text = mappack.emit('games/platformer')
        self.assertIn('game_level_count(void){ return 3; }', text)
        self.assertIn('map_level1_ent', text)
        self.assertIn('256, 30', text)
        attrs = map2c.attribute_bytes(tiles, pal, palmap)
        level_tiles, level_pal, _s, _pm = map2c.load('games/platformer/maps/level1.txt')
        level_attrs = map2c.attribute_bytes(level_tiles, level_pal, None)
        golden = open('editor/tests/golden/level.c').read()
        line = [ln for ln in golden.splitlines() if ln.startswith('const unsigned char map_level_attr')][0]
        nums = [int(n) for n in line.split('{', 1)[1].split('}')[0].split(',') if n]
        self.assertEqual(level_attrs, nums)
        self.assertEqual(len(attrs), (256 // 32) * 64)
        names = mappack.read_order('games/platformer')
        self.assertEqual(names, ['level1', 'level2', 'long'])
        self.assertEqual(mappack.read_order('games/breakout'), ['play'])

    def test_overwide_map_is_an_error(self):
        folder = tempfile.mkdtemp()
        try:
            game = os.path.join(folder, 'wide')
            os.makedirs(os.path.join(game, 'maps'))
            rows = ['.' * 513 for _ in range(30)]
            open(os.path.join(game, 'maps', 'big.txt'), 'w').write(
                'legend:\n. 0x20 pal=0\nmap:\n' + '\n'.join(rows) + '\n')
            open(os.path.join(game, 'maps', 'order.txt'), 'w').write('big\n')
            open(os.path.join(game, 'songs.txt'), 'w').write('song play\ntempo 120\n')
            with self.assertRaises(SystemExit):
                mappack.emit(game)
            short = ['.' * 32 for _ in range(20)]
            open(os.path.join(game, 'maps', 'big.txt'), 'w').write(
                'legend:\n. 0x20 pal=0\nmap:\n' + '\n'.join(short) + '\n')
            with self.assertRaises(SystemExit):
                mappack.emit(game)
        finally:
            shutil.rmtree(folder)

    def test_map_list_create_rename_duplicate_reorder_delete(self):
        folder = tempfile.mkdtemp()
        try:
            root = re_data.create_project(folder, 'blank', None)
            project = re_data.Project(root)
            self.assertEqual([m.name for m in project.maps], ['level'])
            project.add_map('second', 128, project.maps[0])
            project.duplicate_map('level')
            self.assertEqual([m.name for m in project.maps], ['level', 'level_copy', 'second'])
            self.assertEqual(project.map_by_name('second').w, 128)
            self.assertEqual(project.map_by_name('second').h, 30)
            project.move_map('second', -1)
            self.assertEqual(project.maps[1].name, 'second')
            project.rename_map('second', 'renamed')
            self.assertIsNone(next((m for m in project.maps if m.name == 'second'), None))
            self.assertEqual(project.map_by_name('renamed').w, 128)
            with self.assertRaises(ValueError):
                project.add_map('renamed', 64, None)
            with self.assertRaises(ValueError):
                project.add_map('bad-name', 64, None)
            with self.assertRaises(ValueError):
                project.add_map('wide', 40, None)
            with self.assertRaises(ValueError):
                project.add_map('too', 544, None)
            project.delete_map('level_copy')
            self.assertEqual([m.name for m in project.maps], ['level', 'renamed'])
            project.delete_map('level')
            with self.assertRaises(ValueError):
                project.delete_map('renamed')
            self.assertEqual([m.name for m in project.maps], ['renamed'])
            project.save()
            again = re_data.Project(root)
            self.assertEqual([m.name for m in again.maps], ['renamed'])
            self.assertEqual(again.map_by_name('renamed').w, 128)
            self.assertFalse(os.path.exists(os.path.join(root, 'maps', 'level.txt')))
            # long map still edits one cell without touching the others
            long_map = re_data.load_map('games/platformer/maps/long.txt')
            before = long_map.tile_at(10, 10)
            long_map.place(10, 10, 0x85, 2)
            self.assertEqual(long_map.tile_at(10, 10), 0x85)
            self.assertEqual(long_map.w, 256)
            state = long_map.copy_state()
            long_map.place(10, 10, before, 0)
            long_map.restore_state(state)
            self.assertEqual(long_map.tile_at(10, 10), 0x85)
        finally:
            shutil.rmtree(folder)

    def test_stream_window_matches_the_long_map(self):
        tiles, pal, _solid, _palmap = map2c.load('games/platformer/maps/long.txt')
        w = len(tiles[0])
        cols = [[tiles[y][x] for y in range(30)] for x in range(w)]
        attrs = map2c.attribute_bytes(tiles, pal, None)
        nt = [[0] * 64 for _ in range(30)]
        at = [[0] * 64 for _ in range(2)]

        def paint(c):
            x = c & 63
            for y in range(30):
                nt[y][x] = cols[c][y]
            page = (c & 63) >> 5
            for ay in range(8):
                idx = ay * 8 + ((c & 31) >> 2)
                at[page][idx] = attrs[(c >> 5) * 64 + idx]

        right = min(63, w - 1)
        for c in range(right + 1):
            paint(c)
        max_cam = (w - 32) * 8
        for cam in list(range(0, max_cam + 1, 3)) + list(range(max_cam, -1, -5)):
            need_l = cam >> 3
            need_r = min(w - 1, (cam + 255) >> 3)
            win_l = right - 63 if right >= 63 else 0
            if need_l >= win_l and need_r <= right:
                pass
            elif need_r > right and need_r - right <= 2:
                while right < need_r:
                    right += 1
                    paint(right)
            elif right > need_l + 63 and right - (need_l + 63) <= 2:
                while need_l + 63 < right:
                    paint(right - 64)
                    right -= 1
            else:
                start = need_r - 63 if need_r >= 63 else 0
                for c in range(start, need_r + 1):
                    paint(c)
                right = need_r
            scroll = cam & 511
            for x in (0, 64, 128, 200, 248):
                world = (cam + x) >> 3
                nt_x = ((x + scroll) & 511) >> 3
                self.assertEqual(nt[26][nt_x], cols[world][26])
                idx = (26 >> 2) * 8 + ((nt_x & 31) >> 2)
                self.assertEqual(at[nt_x >> 5][idx], attrs[(world >> 5) * 64 + idx])


if __name__ == '__main__':
    unittest.main()
