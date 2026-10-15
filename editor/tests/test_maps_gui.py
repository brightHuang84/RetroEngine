#!/usr/bin/env python3
"""Headless checks for the map list and editing a 256-column map."""
import os
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


def grab(widget, name):
    QTest.qWait(30)
    widget.grab().save(os.path.join(OUT, name))
    print('shot', name)


def main():
    app = QApplication([])
    retro_editor.apply_style(app)
    window = retro_editor.MainWindow(ROOT)
    window.resize(1200, 780)
    window.show()
    window.open_project(os.path.join(ROOT, 'games', 'platformer'))
    window.tabs.setCurrentIndex(2)
    tab = window.map_tab
    names = [tab.map_box.itemData(i) for i in range(tab.map_box.count())]
    if names != ['level1', 'level2', 'long']:
        raise SystemExit('map list is %s' % names)
    grab(window, 'platformer_map_list.png')
    long_index = names.index('long')
    tab.map_box.setCurrentIndex(long_index)
    QTest.qWait(30)
    m = tab.current()
    if m.name != 'long' or m.w != 256 or m.h != 30:
        raise SystemExit('long map is %s %dx%d' % (m.name, m.w, m.h))
    if tab.scale != 1:
        raise SystemExit('long map scale is %s' % tab.scale)
    area = tab.view.parentWidget().parentWidget()
    area.horizontalScrollBar().setValue(80 * 8)
    grab(window, 'platformer_long_map.png')
    path = m.path
    backup = open(path, 'rb').read()
    others = {}
    for other in window.project.maps:
        if other.path != path:
            others[other.path] = open(other.path, 'rb').read()
    order = open(os.path.join(ROOT, 'games', 'platformer', 'maps', 'order.txt'), 'rb').read()
    try:
        before = m.tile_at(40, 12)
        tab.select_tile(0x85)
        tab.pal = 2
        tab.auto.setChecked(False)
        # A click records history, then paints. paint_cell alone is the drag path.
        tab.begin_stroke()
        tab.paint_cell(40, 12)
        tab._stroke = False
        if m.tile_at(40, 12) != 0x85:
            raise SystemExit('paint did not stick, tile is %s' % m.tile_at(40, 12))
        tab.undo()
        if m.tile_at(40, 12) != before:
            raise SystemExit('undo did not restore the long map')
        tab.redo()
        if m.tile_at(40, 12) != 0x85:
            raise SystemExit('redo did not restore the paint')
        window.save_all()
        again = open(path).read()
        if '0x85' not in again.split('map:')[1].split('entities:')[0]:
            # the legend already has B 0x85; the row itself must contain B at column 40
            row = again.split('map:')[1].split('entities:')[0].strip().splitlines()[12]
            if len(row) != 256 or row[40] == backup.decode().split('map:')[1].split('entities:')[0].strip().splitlines()[12][40]:
                raise SystemExit('saved long map row 12 did not change at column 40: %s' % row[40])
        reloaded = retro_editor.data.load_map(path)
        if reloaded.tile_at(40, 12) != 0x85 or reloaded.w != 256:
            raise SystemExit('reload lost the long-map edit')
        for other_path, blob in others.items():
            if open(other_path, 'rb').read() != blob:
                raise SystemExit('editing the long map rewrote %s' % other_path)
        if open(os.path.join(ROOT, 'games', 'platformer', 'maps', 'order.txt'), 'rb').read() != order:
            raise SystemExit('order.txt changed')
        print('long map edit ok')
    finally:
        open(path, 'wb').write(backup)
        window.project.dirty['maps'] = False
    print('maps gui ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
