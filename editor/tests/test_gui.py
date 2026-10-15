#!/usr/bin/env python3
"""Open the editor offscreen, grab each tab, edit, rebuild, and check the picture."""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '0')
sys.path.insert(0, os.path.join(ROOT, 'editor'))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

import retro_editor

OUT = os.environ.get('EDITOR_SHOTS', '/opt/cursor/artifacts/editor')
os.makedirs(OUT, exist_ok=True)


def grab(window, name):
    QTest.qWait(50)
    window.grab().save(os.path.join(OUT, name))
    print('shot', name)


def show_tabs(window, prefix):
    titles = ['tiles', 'palette', 'map', 'music', 'preview', 'code', 'build']
    for i, title in enumerate(titles):
        window.tabs.setCurrentIndex(i)
        grab(window, '%s_%s.png' % (prefix, title))


def shot_game(binary, dest):
    env = os.environ.copy()
    env.update({'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
    env['RETRO_TEST'] = dest
    env['RETRO_SHOT_A'] = '60'
    env['RETRO_SHOT_B'] = '150'
    env['RETRO_WAV'] = dest + '.wav'
    env['RETRO_FRAMES'] = '150'
    subprocess.check_call([binary], env=env)


def main():
    app = QApplication([])
    retro_editor.apply_style(app)
    window = retro_editor.MainWindow(ROOT)
    window.resize(1200, 780)
    window.show()
    window.open_project(os.path.join(ROOT, 'games', 'breakout'))
    show_tabs(window, 'breakout')
    window.open_project(os.path.join(ROOT, 'games', 'platformer'))
    show_tabs(window, 'platformer')

    window.open_project(os.path.join(ROOT, 'games', 'breakout'))
    binary = os.path.join(ROOT, 'build', 'breakout', 'pc', 'breakout')
    before = os.path.join(OUT, 'game_before')
    shot_game(binary, before)

    backups = {}
    paths = [
        os.path.join(ROOT, 'games', 'breakout', 'tiles.png'),
        os.path.join(ROOT, 'games', 'breakout', 'play.txt'),
        os.path.join(ROOT, 'games', 'breakout', 'songs.txt'),
    ]
    for path in paths:
        backups[path] = open(path, 'rb').read()
    try:
        window.tabs.setCurrentIndex(0)
        window.tile_tab.select_tile(0x82)
        window.tile_tab.pen = 3
        window.tile_tab.paint_pixel(0, 0)
        window.tile_tab.paint_pixel(1, 0)
        window.tile_tab.paint_pixel(0, 1)
        window.tabs.setCurrentIndex(2)
        window.map_tab.select_tile(0x82)
        window.map_tab.pal = 3
        window.map_tab.auto.setChecked(True)
        window.map_tab.paint_cell(8, 20)
        window.tabs.setCurrentIndex(3)
        window.music_tab.songs.setCurrentRow(0)
        window.music_tab.chan.setCurrentIndex(0)
        note, dur = window.music_tab.channel().events[0]
        window.music_tab.channel().events[0] = ('C3', dur)
        window.project.dirty['songs'] = True
        window.music_tab.reload_table()
        window.music_tab.play()
        QTest.qWait(100)
        window.music_tab.stop()
        grab(window, 'breakout_music_edited.png')
        window.save_all()
        text = open(paths[2]).read()
        if 'C3' not in text.split('song play')[0]:
            raise SystemExit('edited note was not saved')
        window.tabs.setCurrentIndex(6)
        window.build_done[:] = []
        window.build_tab.start('pc')
        for _ in range(200):
            QTest.qWait(100)
            if window.build_done:
                break
        if not window.build_done or window.build_done[-1] != 0:
            raise SystemExit('PC build failed:\n' + window.build_tab.log.toPlainText()[-2000:])
        grab(window, 'breakout_build.png')
        after = os.path.join(OUT, 'game_after')
        shot_game(binary, after)
        before_px = open(before + '_b.bmp', 'rb').read()
        after_px = open(after + '_b.bmp', 'rb').read()
        if before_px == after_px:
            raise SystemExit('edited game screenshot matches the original')
        before_wav = open(before + '.wav', 'rb').read()
        after_wav = open(after + '.wav', 'rb').read()
        if before_wav == after_wav:
            raise SystemExit('edited song produced the same audio')
        from PIL import Image
        Image.open(before + '_b.bmp').save(os.path.join(OUT, 'game_before_b.png'))
        Image.open(after + '_b.bmp').save(os.path.join(OUT, 'game_after_b.png'))
        print('edit visible in screenshot and wav')
    finally:
        for path, blob in backups.items():
            open(path, 'wb').write(blob)
        subprocess.check_call(['make', 'GAME=breakout', 'pc'])
    print('gui ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
