#!/usr/bin/env python3
"""Offscreen checks for the script and animation tabs."""
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

OUT = os.environ.get('EDITOR_SHOTS', '/tmp/shots')
os.makedirs(OUT, exist_ok=True)


def grab(window, name):
    QTest.qWait(30)
    path = os.path.join(OUT, name)
    window.grab().save(path)
    print('shot', path)


def main():
    app = QApplication([])
    retro_editor.apply_style(app)
    window = retro_editor.MainWindow(ROOT)
    window.resize(1200, 780)
    window.show()
    window.open_project(os.path.join(ROOT, 'games', 'platformer'))
    window.tabs.setCurrentIndex(7)
    grab(window, 'editor_scripts.png')
    before = len(window.project.scripts['scripts'][0]['blocks'])
    window.script_tab.add_block('set', inside=False)
    window.project.scripts['scripts'][0]['blocks'][-1]['var'] = ''
    errors = window.script_tab.check_compile()
    if not any('未知变量' in err for err in errors):
        raise SystemExit('expected a Chinese unknown-variable error, got %r' % errors)
    window.script_tab.delete_block()
    # The new block may not be selected after rebuild. Drop a trailing empty set if it remains.
    blocks = window.project.scripts['scripts'][0]['blocks']
    if blocks and blocks[-1].get('op') == 'set' and not blocks[-1].get('var'):
        blocks.pop()
    errors = window.script_tab.check_compile()
    if errors:
        raise SystemExit('platformer scripts failed after undo: %s' % errors)
    if len(window.project.scripts['scripts'][0]['blocks']) != before:
        raise SystemExit('block count changed')
    window.script_tab.add_block('sfx', inside=False)
    added = window.project.scripts['scripts'][0]['blocks'][-1]
    if added.get('op') != 'sfx':
        raise SystemExit('palette did not append a sound block')
    window.project.scripts['scripts'][0]['blocks'].pop()
    window.project.dirty['scripts'] = False

    window.tabs.setCurrentIndex(8)
    grab(window, 'editor_anims.png')
    anim = window.anim_tab
    meta = anim.current_meta()
    if not meta or len(meta.get('parts') or []) < 2:
        raise SystemExit('platformer metasprite did not load')
    warnings = animc_warnings(meta)
    if warnings:
        raise SystemExit('idle frame should fit the sprite limits: %s' % warnings)
    # A 9-high stack is over the scanline limit. Restore the original parts after.
    saved = [dict(p) for p in meta['parts']]
    meta['parts'] = [{'dx': i * 8, 'dy': 0, 'tile': 1, 'attr': 0} for i in range(9)]
    anim._refresh_warn()
    if '扫描线' not in anim.warn.text():
        raise SystemExit('scanline warning missing: %s' % anim.warn.text())
    meta['parts'] = saved
    anim._refresh_warn()
    errors = anim.check_compile()
    if errors:
        raise SystemExit('animation check failed: %s' % errors)
    window.anim_tab.flip.setChecked(True)
    window.anim_tab.onion.setChecked(True)
    window.anim_tab.zoom.setValue(6)
    grab(window, 'editor_anims_flip.png')
    if window.project.dirty['anims'] or window.project.dirty['scripts']:
        raise SystemExit('editor test dirtied the project')
    print('gui script/anim ok')
    return 0


def animc_warnings(meta):
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import animc
    return animc.frame_warnings(meta.get('parts') or [])


if __name__ == '__main__':
    sys.exit(main())
