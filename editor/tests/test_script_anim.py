#!/usr/bin/env python3
"""Script compiler and animation table tests. No Qt."""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'editor'))

import animc
import scriptc
import re_data


class ScriptTests(unittest.TestCase):
    def test_platformer_compiles(self):
        game = os.path.join(ROOT, 'games', 'platformer')
        doc = scriptc.load(os.path.join(game, 'scripts.json'))
        ctx = scriptc.context(game)
        errors = scriptc.check(doc, ctx)
        self.assertEqual(errors, [])
        prog = scriptc.compile_doc(doc, ctx)
        self.assertGreaterEqual(len(prog['metas']), 4)
        self.assertIn(scriptc.OP_SFX, prog['code'])
        self.assertIn(scriptc.OP_HOOK, prog['code'])
        self.assertIn(scriptc.OP_LEVEL, prog['code'])
        self.assertIn('HI', prog['strings'])
        self.assertIn('got', prog['lnames'])
        self.assertIn('score', prog['hooks'])

    def test_blocks_compiles_and_roundtrips(self):
        game = os.path.join(ROOT, 'games', 'blocks')
        doc = scriptc.load(os.path.join(game, 'scripts.json'))
        text = scriptc.dump(doc)
        again = json.loads(text)
        self.assertEqual(again['scripts'][0]['event'], 'frame')
        ctx = scriptc.context(game)
        prog = scriptc.compile_doc(doc, ctx)
        self.assertIn(scriptc.OP_JNHELD, prog['code'])
        self.assertIn(scriptc.OP_MOVE, prog['code'])
        self.assertIn(scriptc.OP_WAIT, prog['code'])
        self.assertIn(scriptc.OP_WIN, prog['code'])
        c_text, h_text = scriptc.emit_sources(doc, ctx)
        self.assertIn('scount = 2', c_text)
        self.assertIn('GOT IT', c_text)

    def test_unknown_variable_is_chinese(self):
        doc = scriptc.empty_doc()
        doc['scripts'].append(scriptc.new_script())
        doc['scripts'][0]['blocks'].append(scriptc.new_block('set'))
        doc['scripts'][0]['blocks'][0]['var'] = 'missing'
        errors = scriptc.check(doc, {'entities': {}, 'songs': [], 'anims': [], 'levels': []})
        self.assertTrue(any('未知变量' in err for err in errors))

    def test_two_variables_only_eq(self):
        doc = scriptc.empty_doc()
        doc['variables'] = [
            {'name': 'a', 'scope': 'global', 'size': 'u8', 'init': 0},
            {'name': 'b', 'scope': 'global', 'size': 'u8', 'init': 0},
        ]
        doc['scripts'].append(scriptc.new_script())
        block = scriptc.new_block('if')
        block['cmp'] = 'lt'
        block['var'] = 'a'
        block['var2'] = 'b'
        doc['scripts'][0]['blocks'].append(block)
        errors = scriptc.check(doc, {'entities': {}, 'songs': [], 'anims': [], 'levels': []})
        self.assertTrue(any('两个变量只能比较是否相等' in err for err in errors))

    def test_add_block_then_compile(self):
        doc = scriptc.empty_doc()
        doc['variables'].append({'name': 'score', 'scope': 'global', 'size': 'u16', 'init': 0})
        script = scriptc.new_script()
        script['name'] = '加分'
        script['blocks'].append(scriptc.new_block('add'))
        script['blocks'][0]['var'] = 'score'
        script['blocks'][0]['value'] = 10
        script['blocks'].append(scriptc.new_block('repeat'))
        script['blocks'][1]['count'] = 3
        script['blocks'][1]['body'].append(scriptc.new_block('sfx'))
        doc['scripts'].append(script)
        ctx = {'entities': {}, 'songs': [], 'anims': [], 'levels': []}
        prog = scriptc.compile_doc(doc, ctx)
        self.assertEqual(prog['code'], [scriptc.OP_ADD, 0, 0, 10, 0,
                                        scriptc.OP_SFX, 3, scriptc.OP_SFX, 3, scriptc.OP_SFX, 3,
                                        scriptc.OP_END])
        folder = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(folder, 'maps'))
            open(os.path.join(folder, 'maps', 'order.txt'), 'w').write('room\n')
            open(os.path.join(folder, 'scripts.json'), 'w').write(scriptc.dump(doc))
            out = os.path.join(folder, 'gen')
            os.makedirs(out)
            scriptc.write(folder, out)
            text = open(os.path.join(out, 'scriptdata.c')).read()
            self.assertIn('const unsigned char scount = 1;', text)
            header = open(os.path.join(out, 'scripts.h')).read()
            self.assertIn('VAR_SCORE', header)
        finally:
            shutil.rmtree(folder)

    def test_project_roundtrip(self):
        folder = tempfile.mkdtemp()
        try:
            root = re_data.create_project(folder, 'blank', None)
            project = re_data.Project(root)
            self.assertEqual(project.scripts['scripts'], [])
            self.assertEqual(project.anims['anims'], [])
            project.scripts['variables'].append(
                {'name': 'lives', 'scope': 'global', 'size': 'u8', 'init': 3})
            project.dirty['scripts'] = True
            project.anims['metas'].append(animc.new_meta('dot'))
            project.anims['anims'].append(animc.new_anim('blink'))
            project.anims['anims'][0]['frames'][0]['meta'] = 'dot'
            project.dirty['anims'] = True
            project.save()
            again = re_data.Project(root)
            self.assertEqual(again.scripts['variables'][0]['name'], 'lives')
            self.assertEqual(again.anims['anims'][0]['name'], 'blink')
            self.assertFalse(again.any_dirty())
        finally:
            shutil.rmtree(folder)


class AnimTests(unittest.TestCase):
    def test_platformer_anims(self):
        game = os.path.join(ROOT, 'games', 'platformer')
        doc = animc.load(os.path.join(game, 'anims.json'))
        self.assertEqual(animc.check(doc), [])
        c_text, h_text = animc.emit_sources(doc, {'player': 1, 'enemy': 3})
        self.assertIn('ANIM_IDLE', h_text)
        self.assertIn('ANIM_RUN', h_text)
        self.assertIn('ANIM_JUMP', h_text)
        self.assertIn('ANIM_WALK', h_text)
        self.assertIn('if(type == 1) return 0;', c_text)
        self.assertIn('if(type == 3) return 3;', c_text)
        again = json.loads(animc.dump(doc))
        self.assertEqual(again['defaults']['player'], 'idle')

    def test_scanline_warning_in_chinese(self):
        parts = [{'dx': 0, 'dy': 0, 'tile': 1, 'attr': 0} for _ in range(9)]
        msgs = animc.frame_warnings(parts)
        self.assertTrue(any('扫描线' in msg and '8' in msg for msg in msgs))
        doc = animc.empty_doc()
        doc['metas'].append({'name': 'crowd', 'parts': parts})
        errors = animc.check(doc)
        self.assertTrue(any('扫描线' in err for err in errors))

    def test_empty_game_still_exports(self):
        c_text, h_text = animc.emit_sources(animc.empty_doc(), {})
        self.assertIn('anim_total = 0', c_text)
        self.assertIn('anim_for_type', c_text)
        self.assertIn('ANIM_NONE 255', h_text)


if __name__ == '__main__':
    unittest.main()
