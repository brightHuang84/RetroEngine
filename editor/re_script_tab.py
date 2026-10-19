"""List-based script editor. The document is project.scripts (scripts.json)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QPushButton, QLabel, QComboBox, QSpinBox, QLineEdit,
    QPlainTextEdit, QFormLayout, QGroupBox, QSplitter, QScrollArea,
)

import scriptc


def _path_key(path):
    return '/'.join(str(p) for p in path)


class ScriptTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.project = None
        self.doc = None
        self._load = False
        self.paths = {}

        root = QVBoxLayout(self)
        top = QSplitter()
        root.addWidget(top, 1)

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.addWidget(QLabel('脚本'))
        self.scripts = QListWidget()
        self.scripts.currentRowChanged.connect(self._script_changed)
        left_lay.addWidget(self.scripts, 1)
        row = QHBoxLayout()
        add = QPushButton('新建脚本')
        add.clicked.connect(self.add_script)
        rem = QPushButton('删除脚本')
        rem.clicked.connect(self.delete_script)
        row.addWidget(add)
        row.addWidget(rem)
        left_lay.addLayout(row)
        self.name = QLineEdit()
        self.name.setPlaceholderText('脚本名字')
        self.name.editingFinished.connect(self._rename)
        left_lay.addWidget(self.name)
        form = QFormLayout()
        self.event = QComboBox()
        for key, label, _num in scriptc.EVENTS:
            self.event.addItem(label, key)
        self.event.currentIndexChanged.connect(self._event_changed)
        self.level = QComboBox()
        self.entity = QComboBox()
        self.button = QComboBox()
        for key in scriptc.BUTTONS:
            self.button.addItem(key, key)
        self.region = QComboBox()
        self.other = QComboBox()
        self.var = QComboBox()
        self.value = QSpinBox()
        self.value.setRange(0, 255)
        self.timer = QSpinBox()
        self.timer.setRange(0, 1)
        self.tile = QSpinBox()
        self.tile.setRange(0, 255)
        for box in (self.level, self.entity, self.button, self.region, self.other, self.var):
            box.currentIndexChanged.connect(self._apply_event)
        self.value.valueChanged.connect(self._apply_event)
        self.timer.valueChanged.connect(self._apply_event)
        self.tile.valueChanged.connect(self._apply_event)
        form.addRow('事件', self.event)
        form.addRow('关卡', self.level)
        form.addRow('实体', self.entity)
        form.addRow('另一个实体', self.other)
        form.addRow('按键', self.button)
        form.addRow('区域', self.region)
        form.addRow('变量', self.var)
        form.addRow('数值', self.value)
        form.addRow('计时器', self.timer)
        form.addRow('图块', self.tile)
        left_lay.addLayout(form)
        top.addWidget(left)

        mid = QWidget()
        mid_lay = QVBoxLayout(mid)
        mid_lay.addWidget(QLabel('积木'))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._block_changed)
        mid_lay.addWidget(self.tree, 1)
        brow = QHBoxLayout()
        inside = QPushButton('放进选中的如果/重复')
        inside.clicked.connect(lambda: self.add_block(self._palette_op(), inside=True))
        dele = QPushButton('删除积木')
        dele.clicked.connect(self.delete_block)
        brow.addWidget(inside)
        brow.addWidget(dele)
        mid_lay.addLayout(brow)
        top.addWidget(mid)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.addWidget(QLabel('积木面板'))
        self.palette = {}
        grid = QHBoxLayout()
        wrap = QWidget()
        pal = QVBoxLayout(wrap)
        for op, label in scriptc.OPS:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, o=op: self.add_block(o, inside=False))
            pal.addWidget(btn)
            self.palette[op] = btn
        pal.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(wrap)
        grid.addWidget(scroll)
        right_lay.addLayout(grid, 1)
        box = QGroupBox('选中的积木')
        self.props = QFormLayout(box)
        self.prop_var = QComboBox()
        self.prop_var2 = QComboBox()
        self.prop_value = QSpinBox()
        self.prop_value.setRange(-32768, 65535)
        self.prop_sfx = QComboBox()
        for key in scriptc.SFX:
            self.prop_sfx.addItem(key, key)
        self.prop_music = QComboBox()
        self.prop_entity = QComboBox()
        self.prop_anim = QComboBox()
        self.prop_level = QComboBox()
        self.prop_scene = QComboBox()
        for key in scriptc.SCENES:
            self.prop_scene.addItem(key, key)
        self.prop_text = QLineEdit()
        self.prop_frames = QSpinBox()
        self.prop_frames.setRange(0, 255)
        self.prop_cmp = QComboBox()
        for key, label in (('eq', '等于'), ('ne', '不等于'), ('lt', '小于'), ('gt', '大于'), ('held', '按住')):
            self.prop_cmp.addItem(label, key)
        self.prop_button = QComboBox()
        for key in scriptc.BUTTONS:
            self.prop_button.addItem(key, key)
        self.prop_count = QSpinBox()
        self.prop_count.setRange(1, 8)
        self.prop_actor = QSpinBox()
        self.prop_actor.setRange(0, 3)
        self.prop_dx = QSpinBox()
        self.prop_dx.setRange(-128, 127)
        self.prop_dy = QSpinBox()
        self.prop_dy.setRange(-128, 127)
        self.prop_x = QSpinBox()
        self.prop_x.setRange(0, 4095)
        self.prop_y = QSpinBox()
        self.prop_y.setRange(0, 255)
        self.prop_hook = QComboBox()
        self.prop_arg = QSpinBox()
        self.prop_arg.setRange(0, 255)
        self.prop_timer = QSpinBox()
        self.prop_timer.setRange(0, 1)
        self._prop_widgets = []
        for widget in (
            self.prop_var, self.prop_var2, self.prop_sfx, self.prop_music, self.prop_entity,
            self.prop_anim, self.prop_level, self.prop_scene, self.prop_cmp, self.prop_button,
            self.prop_hook,
        ):
            widget.currentIndexChanged.connect(self._apply_block)
        for widget in (
            self.prop_value, self.prop_frames, self.prop_count, self.prop_actor, self.prop_dx,
            self.prop_dy, self.prop_x, self.prop_y, self.prop_arg, self.prop_timer,
        ):
            widget.valueChanged.connect(self._apply_block)
        self.prop_text.editingFinished.connect(self._apply_block)
        right_lay.addWidget(box)
        top.addWidget(right)

        bottom = QHBoxLayout()
        vars_box = QGroupBox('变量（全局或本关，u8/u16，运行时都占 16 位）')
        vlay = QVBoxLayout(vars_box)
        self.vars = QListWidget()
        vlay.addWidget(self.vars)
        vrow = QHBoxLayout()
        self.var_name = QLineEdit()
        self.var_name.setPlaceholderText('名字')
        self.var_scope = QComboBox()
        self.var_scope.addItem('全局', 'global')
        self.var_scope.addItem('本关', 'level')
        self.var_size = QComboBox()
        self.var_size.addItem('u8', 'u8')
        self.var_size.addItem('u16', 'u16')
        addv = QPushButton('添加变量')
        addv.clicked.connect(self.add_variable)
        delv = QPushButton('删除变量')
        delv.clicked.connect(self.delete_variable)
        vrow.addWidget(self.var_name)
        vrow.addWidget(self.var_scope)
        vrow.addWidget(self.var_size)
        vrow.addWidget(addv)
        vrow.addWidget(delv)
        vlay.addLayout(vrow)
        bottom.addWidget(vars_box, 1)
        err_box = QVBoxLayout()
        check = QPushButton('检查编译')
        check.clicked.connect(self.check_compile)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumHeight(120)
        err_box.addWidget(check)
        err_box.addWidget(self.errors)
        bottom.addLayout(err_box, 1)
        root.addLayout(bottom)

    def load(self, project):
        self.project = project
        self.doc = project.scripts
        self._fill_context()
        self._reload_scripts()
        self._reload_vars()
        self.errors.setPlainText('')

    def flush(self):
        script = self.current_script()
        if script and not self._load:
            name = self.name.text().strip() or '未命名'
            if script.get('name') != name:
                script['name'] = name
                self.mark()
        self._apply_event()
        self._apply_block()

    def refresh_context(self):
        if self.project:
            self._fill_context()

    def mark(self):
        if self.project:
            self.project.dirty['scripts'] = True
            self.window.touch()

    def _ctx(self):
        if not self.project:
            return {'entities': {}, 'songs': [], 'anims': [], 'levels': []}
        ctx = scriptc.context(self.project.root)
        ctx['entities'] = {t.name: t.id for t in self.project.entity_spec.types}
        ctx['songs'] = [s.name for s in self.project.songs]
        ctx['levels'] = [m.name for m in self.project.maps]
        ctx['anims'] = [a.get('name', '') for a in self.project.anims.get('anims', [])]
        return ctx

    def _fill_context(self):
        ctx = self._ctx()
        self._load = True
        def fill(box, items, empty=''):
            cur = box.currentData()
            box.clear()
            if empty is not None:
                box.addItem(empty, '')
            for item in items:
                box.addItem(str(item), item)
            idx = box.findData(cur)
            if idx >= 0:
                box.setCurrentIndex(idx)
        levels = [m.name for m in self.project.maps] if self.project else ctx['levels']
        ents = list(ctx['entities'].keys())
        anims = [a.get('name', '') for a in (self.project.anims.get('anims') if self.project else [])]
        songs = [s.name for s in self.project.songs] if self.project else ctx['songs']
        regions = [r.get('name', '') for r in self.doc.get('regions', [])]
        variables = [v.get('name', '') for v in self.doc.get('variables', [])]
        hooks = list(self.doc.get('hooks', []))
        fill(self.level, levels, '全部关卡')
        fill(self.entity, ents, '')
        fill(self.other, ents, '')
        fill(self.region, regions, '')
        fill(self.var, variables, '')
        fill(self.prop_var, variables, '')
        fill(self.prop_var2, variables, '（和常数比）')
        fill(self.prop_music, songs, '')
        fill(self.prop_entity, ents, '')
        fill(self.prop_anim, anims, '（不切换）')
        fill(self.prop_level, ['next'] + list(levels), None)
        fill(self.prop_hook, hooks, '')
        self._load = False

    def _reload_vars(self):
        self.vars.clear()
        for var in self.doc.get('variables', []):
            scope = '本关' if var.get('scope') == 'level' else '全局'
            self.vars.addItem('%s  %s %s = %s' % (var.get('name', ''), scope, var.get('size', 'u16'), var.get('init', 0)))

    def _reload_scripts(self):
        self._load = True
        row = self.scripts.currentRow()
        self.scripts.clear()
        for script in self.doc.get('scripts', []):
            label = scriptc.EVENT_BY_NAME.get(script.get('event'), ('', script.get('event', ''), 0))[1]
            self.scripts.addItem('%s  ·  %s' % (script.get('name') or '未命名', label))
        if self.scripts.count():
            self.scripts.setCurrentRow(row if 0 <= row < self.scripts.count() else 0)
        self._load = False
        self._script_changed(self.scripts.currentRow())

    def current_script(self):
        row = self.scripts.currentRow()
        scripts = self.doc.get('scripts', []) if self.doc else []
        if 0 <= row < len(scripts):
            return scripts[row]
        return None

    def add_script(self):
        if self.doc is None:
            return
        self.doc.setdefault('scripts', []).append(scriptc.new_script())
        self.mark()
        self._reload_scripts()
        self.scripts.setCurrentRow(self.scripts.count() - 1)

    def delete_script(self):
        row = self.scripts.currentRow()
        scripts = self.doc.get('scripts', []) if self.doc else []
        if 0 <= row < len(scripts):
            del scripts[row]
            self.mark()
            self._reload_scripts()

    def add_variable(self):
        name = self.var_name.text().strip()
        if not name or self.doc is None:
            return
        self.doc.setdefault('variables', []).append({
            'name': name,
            'scope': self.var_scope.currentData(),
            'size': self.var_size.currentData(),
            'init': 0,
        })
        self.var_name.clear()
        self.mark()
        self._reload_vars()
        self._fill_context()

    def delete_variable(self):
        row = self.vars.currentRow()
        variables = self.doc.get('variables', []) if self.doc else []
        if 0 <= row < len(variables):
            del variables[row]
            self.mark()
            self._reload_vars()
            self._fill_context()

    def _rename(self):
        script = self.current_script()
        if not script or self._load:
            return
        name = self.name.text().strip() or '未命名'
        if script.get('name') == name:
            return
        script['name'] = name
        self.mark()
        self._reload_scripts()

    def _script_changed(self, row):
        script = self.current_script()
        self._load = True
        if not script:
            self.name.clear()
            self.tree.clear()
            self._load = False
            return
        self.name.setText(script.get('name', ''))
        idx = self.event.findData(script.get('event', 'frame'))
        if idx >= 0:
            self.event.setCurrentIndex(idx)
        for box, key in (
            (self.level, 'level'), (self.entity, 'entity'), (self.other, 'other'),
            (self.region, 'region'), (self.var, 'var'), (self.button, 'button'),
        ):
            found = box.findData(script.get(key, ''))
            if found >= 0:
                box.setCurrentIndex(found)
        self.value.setValue(int(script.get('value', 0) or 0))
        self.timer.setValue(int(script.get('timer', 0) or 0))
        self.tile.setValue(int(script.get('tile', 0) or 0))
        self._load = False
        self._rebuild_tree()

    def _event_changed(self):
        self._apply_event()

    def _apply_event(self):
        script = self.current_script()
        if not script or self._load:
            return
        fields = {
            'event': self.event.currentData(),
            'level': self.level.currentData() or '',
            'entity': self.entity.currentData() or '',
            'other': self.other.currentData() or '',
            'region': self.region.currentData() or '',
            'var': self.var.currentData() or '',
            'button': self.button.currentData() or 'a',
            'value': self.value.value(),
            'timer': self.timer.value(),
            'tile': self.tile.value(),
        }
        changed = False
        for key, value in fields.items():
            if script.get(key) != value:
                script[key] = value
                changed = True
        if changed:
            self.mark()

    def _rebuild_tree(self):
        script = self.current_script()
        self.tree.clear()
        self.paths = {}
        if not script:
            return
        self._add_nodes(self.tree.invisibleRootItem(), script.get('blocks') or [], [])
        self.tree.expandAll()

    def _add_nodes(self, parent, blocks, prefix):
        for i, block in enumerate(blocks):
            path = prefix + [i]
            label = scriptc.OP_LABEL.get(block.get('op'), block.get('op'))
            extra = block.get('var') or block.get('id') or block.get('text') or ''
            if extra:
                label = '%s  %s' % (label, extra)
            item = QTreeWidgetItem([label])
            parent.addChild(item)
            self.paths[id(item)] = path
            if block.get('op') == 'if':
                then_item = QTreeWidgetItem(['那么'])
                else_item = QTreeWidgetItem(['否则'])
                item.addChild(then_item)
                item.addChild(else_item)
                self._add_nodes(then_item, block.get('then') or [], path + ['then'])
                self._add_nodes(else_item, block.get('else') or [], path + ['else'])
            elif block.get('op') == 'repeat':
                body = QTreeWidgetItem(['重复内容'])
                item.addChild(body)
                self._add_nodes(body, block.get('body') or [], path + ['body'])

    def _resolve(self, path):
        """Return (container list, index) for a block path."""
        script = self.current_script()
        if script is None:
            return None, None
        container = script.setdefault('blocks', [])
        if not path:
            return container, None
        index = path[0]
        i = 1
        while i < len(path):
            if not isinstance(index, int) or index >= len(container):
                return None, None
            block = container[index]
            key = path[i]
            container = block.setdefault(key, [])
            i += 1
            if i >= len(path):
                return container, None
            index = path[i]
            i += 1
        if not isinstance(index, int) or index >= len(container):
            return None, None
        return container, index

    def current_block(self):
        item = self.tree.currentItem()
        if item is None or id(item) not in self.paths:
            return None
        container, index = self._resolve(self.paths[id(item)])
        if container is None or index is None:
            return None
        return container[index]

    def _palette_op(self):
        return 'set'

    def _container_for_new(self, inside):
        script = self.current_script()
        if script is None:
            return None
        if not inside:
            return script.setdefault('blocks', [])
        item = self.tree.currentItem()
        if item is None or id(item) not in self.paths:
            return script.setdefault('blocks', [])
        path = self.paths[id(item)]
        container, index = self._resolve(path)
        if container is None or index is None:
            return script.setdefault('blocks', [])
        block = container[index]
        if block.get('op') == 'if':
            return block.setdefault('then', [])
        if block.get('op') == 'repeat':
            return block.setdefault('body', [])
        return script.setdefault('blocks', [])

    def add_block(self, op, inside=False):
        container = self._container_for_new(inside)
        if container is None:
            return None
        block = scriptc.new_block(op)
        if op in ('set', 'add', 'rand'):
            names = [v.get('name', '') for v in self.doc.get('variables', [])]
            if names:
                block['var'] = names[0]
        if op == 'if':
            names = [v.get('name', '') for v in self.doc.get('variables', [])]
            if names:
                block['var'] = names[0]
        if op == 'music':
            songs = [s.name for s in self.project.songs] if self.project else []
            if songs:
                block['id'] = songs[0]
        if op in ('spawn', 'actor'):
            ents = list(self._ctx()['entities'].keys())
            if ents:
                block['entity'] = ents[0]
        if op == 'anim':
            anims = [a.get('name', '') for a in (self.project.anims.get('anims') if self.project else [])]
            if anims:
                block['id'] = anims[0]
        if op == 'hook':
            hooks = self.doc.get('hooks') or []
            if hooks:
                block['id'] = hooks[0]
        container.append(block)
        self.mark()
        self._rebuild_tree()
        return block

    def delete_block(self):
        item = self.tree.currentItem()
        if item is None or id(item) not in self.paths:
            return
        container, index = self._resolve(self.paths[id(item)])
        if container is None or index is None:
            return
        del container[index]
        self.mark()
        self._rebuild_tree()

    def _clear_props(self):
        while self.props.rowCount():
            self.props.removeRow(0)

    def _block_changed(self, *_args):
        self._load = True
        self._clear_props()
        block = self.current_block()
        if not block:
            self._load = False
            return
        op = block.get('op')
        def row(label, widget):
            self.props.addRow(label, widget)
        if op in ('set', 'add', 'rand'):
            self._select(self.prop_var, block.get('var', ''))
            row('变量', self.prop_var)
            if op != 'rand':
                self.prop_value.setValue(int(block.get('value', 0) or 0))
                row('数值', self.prop_value)
            else:
                self.prop_value.setValue(int(block.get('max', 2) or 2))
                row('上限', self.prop_value)
        elif op == 'sfx':
            self._select(self.prop_sfx, block.get('id', 'coin'))
            row('音效', self.prop_sfx)
        elif op == 'music':
            self._select(self.prop_music, block.get('id', ''))
            row('乐曲', self.prop_music)
        elif op == 'spawn':
            self._select(self.prop_entity, block.get('entity', ''))
            self.prop_x.setValue(int(block.get('x', 0) or 0))
            self.prop_y.setValue(int(block.get('y', 0) or 0))
            row('实体', self.prop_entity)
            row('x', self.prop_x)
            row('y', self.prop_y)
        elif op == 'move':
            self.prop_actor.setValue(int(block.get('actor', 0) or 0))
            self.prop_dx.setValue(int(block.get('dx', 0) or 0))
            self.prop_dy.setValue(int(block.get('dy', 0) or 0))
            row('角色槽', self.prop_actor)
            row('dx', self.prop_dx)
            row('dy', self.prop_dy)
        elif op == 'anim':
            self.prop_actor.setValue(int(block.get('actor', 0) or 0))
            self._select(self.prop_anim, block.get('id', ''))
            row('角色槽', self.prop_actor)
            row('动画', self.prop_anim)
        elif op == 'level':
            self._select(self.prop_level, block.get('id', 'next'))
            row('关卡', self.prop_level)
        elif op == 'scene':
            self._select(self.prop_scene, block.get('id', 'play'))
            row('场景', self.prop_scene)
        elif op == 'text':
            self.prop_text.setText(str(block.get('text', '')))
            self.prop_frames.setValue(int(block.get('frames', 90) or 0))
            row('文字', self.prop_text)
            row('帧数', self.prop_frames)
        elif op in ('wait', 'shake'):
            self.prop_frames.setValue(int(block.get('frames', 30) or 0))
            row('帧数', self.prop_frames)
        elif op == 'if':
            self._select(self.prop_cmp, block.get('cmp', 'eq'))
            self._select(self.prop_var, block.get('var', ''))
            self._select(self.prop_var2, block.get('var2', ''))
            self.prop_value.setValue(int(block.get('value', 0) or 0))
            self._select(self.prop_button, block.get('button', 'right'))
            row('比较', self.prop_cmp)
            row('变量', self.prop_var)
            row('另一个变量', self.prop_var2)
            row('常数', self.prop_value)
            row('按键', self.prop_button)
        elif op == 'repeat':
            self.prop_count.setValue(int(block.get('count', 2) or 2))
            row('次数', self.prop_count)
        elif op == 'hook':
            self._select(self.prop_hook, block.get('id', ''))
            self.prop_arg.setValue(int(block.get('arg', 0) or 0))
            row('函数', self.prop_hook)
            row('参数', self.prop_arg)
        elif op == 'timer':
            self.prop_timer.setValue(int(block.get('id', 0) or 0))
            self.prop_frames.setValue(int(block.get('frames', 60) or 0))
            row('编号', self.prop_timer)
            row('帧数', self.prop_frames)
        elif op == 'actor':
            self.prop_actor.setValue(int(block.get('actor', 0) or 0))
            self._select(self.prop_entity, block.get('entity', ''))
            self.prop_x.setValue(int(block.get('x', 0) or 0))
            self.prop_y.setValue(int(block.get('y', 0) or 0))
            self._select(self.prop_anim, block.get('anim', ''))
            row('角色槽', self.prop_actor)
            row('实体', self.prop_entity)
            row('x', self.prop_x)
            row('y', self.prop_y)
            row('动画', self.prop_anim)
        self._load = False

    def _select(self, box, value):
        idx = box.findData(value)
        if idx < 0:
            idx = box.findText(str(value))
        if idx >= 0:
            box.setCurrentIndex(idx)

    def _apply_block(self):
        block = self.current_block()
        if not block or self._load:
            return
        before = {k: block[k] for k in block if k not in ('then', 'else', 'body')}
        op = block.get('op')
        if op in ('set', 'add'):
            block['var'] = self.prop_var.currentData() or ''
            block['value'] = self.prop_value.value()
        elif op == 'rand':
            block['var'] = self.prop_var.currentData() or ''
            block['max'] = self.prop_value.value()
        elif op == 'sfx':
            block['id'] = self.prop_sfx.currentData()
        elif op == 'music':
            block['id'] = self.prop_music.currentData() or ''
        elif op == 'spawn':
            block['entity'] = self.prop_entity.currentData() or ''
            block['x'] = self.prop_x.value()
            block['y'] = self.prop_y.value()
        elif op == 'move':
            block['actor'] = self.prop_actor.value()
            block['dx'] = self.prop_dx.value()
            block['dy'] = self.prop_dy.value()
        elif op == 'anim':
            block['actor'] = self.prop_actor.value()
            block['id'] = self.prop_anim.currentData() or ''
        elif op == 'level':
            block['id'] = self.prop_level.currentData() or 'next'
        elif op == 'scene':
            block['id'] = self.prop_scene.currentData() or 'play'
        elif op == 'text':
            block['text'] = self.prop_text.text()
            block['frames'] = self.prop_frames.value()
        elif op in ('wait', 'shake'):
            block['frames'] = self.prop_frames.value()
        elif op == 'if':
            block['cmp'] = self.prop_cmp.currentData()
            block['var'] = self.prop_var.currentData() or ''
            block['var2'] = self.prop_var2.currentData() or ''
            block['value'] = self.prop_value.value()
            block['button'] = self.prop_button.currentData() or 'right'
        elif op == 'repeat':
            block['count'] = self.prop_count.value()
        elif op == 'hook':
            block['id'] = self.prop_hook.currentData() or ''
            block['arg'] = self.prop_arg.value()
        elif op == 'timer':
            block['id'] = self.prop_timer.value()
            block['frames'] = self.prop_frames.value()
        elif op == 'actor':
            block['actor'] = self.prop_actor.value()
            block['entity'] = self.prop_entity.currentData() or ''
            block['x'] = self.prop_x.value()
            block['y'] = self.prop_y.value()
            block['anim'] = self.prop_anim.currentData() or ''
        after = {k: block[k] for k in block if k not in ('then', 'else', 'body')}
        if after != before:
            self.mark()

    def check_compile(self):
        if not self.project:
            return []
        self.flush()
        errors = scriptc.check(self.doc, self._ctx())
        if errors:
            self.errors.setPlainText('\n'.join(errors))
        else:
            prog = scriptc.compile_doc(self.doc, self._ctx())
            self.errors.setPlainText('脚本检查通过（%d 条脚本，%d 字节）' % (
                len(prog['metas']), len(prog['code'])))
        return errors
