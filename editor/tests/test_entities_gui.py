#!/usr/bin/env python3
"""Place a coin, move the platformer enemy, rebuild, and check the PC frame."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '0')
sys.path.insert(0, os.path.join(ROOT, 'editor'))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

import retro_editor

OUT = os.environ.get('EDITOR_SHOTS', '/opt/cursor/artifacts/editor')
os.makedirs(OUT, exist_ok=True)


def grab(widget, name):
    QTest.qWait(50)
    widget.grab().save(os.path.join(OUT, name))
    print('shot', name)


def shot_game(binary, dest):
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy',
        'RETRO_TEST': dest, 'RETRO_SHOT_A': '40', 'RETRO_SHOT_B': '180',
        'RETRO_FRAMES': '180',
    })
    subprocess.check_call([binary], env=env)


def main():
    app = QApplication([])
    retro_editor.apply_style(app)
    window = retro_editor.MainWindow(ROOT)
    window.resize(1200, 780)
    window.show()
    window.open_project(os.path.join(ROOT, 'games', 'platformer'))
    window.tabs.setCurrentIndex(2)
    window.map_tab.mode_box.setCurrentIndex(1)
    QTest.qWait(50)
    area = window.map_tab.view.parentWidget().parentWidget()
    area.verticalScrollBar().setValue(150 * window.map_tab.scale)
    area.horizontalScrollBar().setValue(0)
    grab(window, 'platformer_entities.png')
    dialog = retro_editor.EntityTypeDialog(window.project, window)
    dialog.show()
    grab(dialog, 'platformer_entity_types.png')
    dialog.close()

    music = window.music_tab
    before_n = len(music.channel().events)
    before_tempo = music.song().tempo
    music.add_row()
    if len(music.channel().events) != before_n + 1:
        raise SystemExit('music add_row did not append')
    music.undo()
    if len(music.channel().events) != before_n:
        raise SystemExit('music undo did not remove the row')
    music.redo()
    if len(music.channel().events) != before_n + 1:
        raise SystemExit('music redo did not restore the row')
    music.undo()
    music._push()
    music.song().tempo = before_tempo + 7
    music.undo()
    if music.song().tempo != before_tempo:
        raise SystemExit('music tempo undo failed')
    window.project.dirty['songs'] = False
    window.tabs.setCurrentIndex(2)

    level = os.path.join(ROOT, 'games', 'platformer', 'level.txt')
    backup = open(level, 'rb').read()
    binary = os.path.join(ROOT, 'build', 'platformer', 'pc', 'platformer')
    subprocess.check_call(['make', 'GAME=platformer', 'pc'])
    before_shot = os.path.join(OUT, 'entity_before')
    shot_game(binary, before_shot)
    try:
        tab = window.map_tab
        m = tab.current()
        if m.name != 'level':
            raise SystemExit('expected level map, got %s' % m.name)
        before = len(m.entities)
        for i in range(tab.type_list.count()):
            if tab.type_list.item(i).data(Qt.ItemDataRole.UserRole) == 'coin':
                tab.type_list.setCurrentRow(i)
        # Empty spot on the first screen: world (40, 136), snapped to the 8px grid.
        QTest.mouseClick(tab.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(40 * tab.scale + 1, 136 * tab.scale + 1))
        if len(m.entities) != before + 1 or m.entities[-1].type != 'coin':
            raise SystemExit('click did not place a coin: %s' % [(e.type, e.x, e.y) for e in m.entities])
        if (m.entities[-1].x, m.entities[-1].y) != (40, 136):
            raise SystemExit('coin did not snap to (%d,%d)' % (m.entities[-1].x, m.entities[-1].y))
        tab.undo()
        if len(m.entities) != before:
            raise SystemExit('undo did not remove the coin')
        tab.redo()
        if len(m.entities) != before + 1:
            raise SystemExit('redo did not restore the coin')
        enemy = next(i for i, ent in enumerate(m.entities) if ent.type == 'enemy')
        QTest.mousePress(tab.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                         QPoint(280 * tab.scale + 2, 200 * tab.scale + 2))
        QTest.mouseMove(tab.view, QPoint(80 * tab.scale + 2, 200 * tab.scale + 2))
        QTest.mouseRelease(tab.view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                           QPoint(80 * tab.scale + 2, 200 * tab.scale + 2))
        ent = m.entities[enemy]
        if (ent.x, ent.y) != (80, 200):
            raise SystemExit('enemy did not move to (80,200), got (%d,%d)' % (ent.x, ent.y))
        tab.selected = enemy
        tab._prop_sig = None
        tab.refresh()
        tab._prop_spins['left'].setValue(40)
        tab._prop_spins['right'].setValue(160)
        if ent.props.get('left') != 40 or ent.props.get('right') != 160:
            raise SystemExit('patrol props were not edited: %s' % ent.props)
        grab(window, 'platformer_entities_edited.png')
        window.tabs.setCurrentIndex(4)
        grab(window, 'platformer_preview_entities.png')
        window.save_all()
        text = open(level).read()
        if 'coin 40 136' not in text or 'enemy 80 200' not in text or 'left=40' not in text:
            raise SystemExit('saved map is missing the edit:\n' + text.split('entities:')[-1])
        window.tabs.setCurrentIndex(6)
        window.build_done[:] = []
        window.build_tab.start('pc')
        for _ in range(200):
            QTest.qWait(100)
            if window.build_done:
                break
        if not window.build_done or window.build_done[-1] != 0:
            raise SystemExit('PC build failed:\n' + window.build_tab.log.toPlainText()[-2000:])
        code = open(os.path.join(ROOT, 'build', 'platformer', 'gen', 'maps.c')).read()
        if '40,136' not in code.replace(' ', '') and '40, 136' not in code:
            # packed bytes: type 2, x=40, y=136
            if '2,40,0,136' not in code.replace(' ', ''):
                raise SystemExit('generated table has no coin at 40,136')
        if '3,80,0,200' not in code.replace(' ', ''):
            raise SystemExit('generated table has no enemy at 80,200')
        dest = os.path.join(OUT, 'entity_edit')
        shot_game(binary, dest)
        from PIL import Image
        base = Image.open(before_shot + '_b.bmp')
        got = Image.open(dest + '_b.bmp')
        if list(base.getdata()) == list(got.getdata()):
            raise SystemExit('moved enemy and new coin did not change the frame')
        got.save(os.path.join(OUT, 'platformer_entity_edit_b.png'))
        base.save(os.path.join(OUT, 'platformer_entity_base_b.png'))
        print('entity edit visible')
    finally:
        open(level, 'wb').write(backup)
        window.project.dirty['maps'] = False
        subprocess.check_call(['make', 'GAME=platformer', 'pc'])
    print('entity gui ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
