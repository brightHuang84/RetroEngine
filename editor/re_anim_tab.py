"""Metasprite and animation editor. The document is project.anims (anims.json)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QComboBox,
    QSpinBox, QLineEdit, QCheckBox, QPlainTextEdit, QFormLayout, QGroupBox, QSplitter,
)

import animc
import re_data as data


class Preview(QWidget):
    def __init__(self, tab):
        QWidget.__init__(self)
        self.tab = tab
        self.setMinimumSize(280, 280)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#111'))
        tab = self.tab
        if not tab.project:
            painter.end()
            return
        zoom = tab.zoom.value()
        parts = tab.preview_parts()
        onion = tab.onion_parts() if tab.onion.isChecked() else None
        flip = tab.flip.isChecked()
        ox = self.width() // 2
        oy = self.height() // 2
        if onion:
            self._draw_parts(painter, onion, ox, oy, zoom, flip, 70)
        self._draw_parts(painter, parts, ox, oy, zoom, flip, 255)
        painter.setPen(QColor('#666'))
        painter.drawLine(ox - 4, oy, ox + 4, oy)
        painter.drawLine(ox, oy - 4, ox, oy + 4)
        painter.end()

    def _draw_parts(self, painter, parts, ox, oy, zoom, flip, alpha):
        tiles = self.tab.project.tiles
        pal = self.tab.project.palette
        for part in parts:
            dx = int(part.get('dx', 0) or 0)
            dy = int(part.get('dy', 0) or 0)
            tile = int(part.get('tile', 0) or 0) & 255
            attr = int(part.get('attr', 0) or 0)
            hflip = bool(attr & 0x40) ^ bool(flip)
            vflip = bool(attr & 0x80)
            spal = (attr & 3)
            if flip:
                dx = -dx - 8
            for y in range(8):
                for x in range(8):
                    sx = 7 - x if hflip else x
                    sy = 7 - y if vflip else y
                    val = tiles.tile_get(tile, sx, sy)
                    if val == 0:
                        continue
                    idx = pal[16 + spal * 4 + val]
                    rgb = data.rgb_of(idx)
                    color = QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255, alpha)
                    painter.fillRect(ox + (dx + x) * zoom, oy + (dy + y) * zoom, zoom, zoom, color)


class AnimTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.project = None
        self.doc = None
        self._load = False
        self.frame_i = 0
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._tick)

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel('元精灵'))
        self.metas = QListWidget()
        self.metas.currentRowChanged.connect(self._meta_changed)
        left.addWidget(self.metas, 1)
        row = QHBoxLayout()
        addm = QPushButton('新建元精灵')
        addm.clicked.connect(self.add_meta)
        delm = QPushButton('删除')
        delm.clicked.connect(self.delete_meta)
        row.addWidget(addm)
        row.addWidget(delm)
        left.addLayout(row)
        self.meta_name = QLineEdit()
        self.meta_name.setPlaceholderText('元精灵名字')
        self.meta_name.editingFinished.connect(self._rename_meta)
        left.addWidget(self.meta_name)
        left.addWidget(QLabel('图块（dx dy 图块 属性）'))
        self.parts = QListWidget()
        self.parts.currentRowChanged.connect(self._part_changed)
        left.addWidget(self.parts, 1)
        form = QFormLayout()
        self.dx = QSpinBox()
        self.dx.setRange(-128, 127)
        self.dy = QSpinBox()
        self.dy.setRange(-128, 127)
        self.tile = QSpinBox()
        self.tile.setRange(0, 255)
        self.attr = QSpinBox()
        self.attr.setRange(0, 255)
        for box in (self.dx, self.dy, self.tile, self.attr):
            box.valueChanged.connect(self._apply_part)
        form.addRow('dx', self.dx)
        form.addRow('dy', self.dy)
        form.addRow('图块', self.tile)
        form.addRow('属性', self.attr)
        left.addLayout(form)
        prow = QHBoxLayout()
        addp = QPushButton('加一块')
        addp.clicked.connect(self.add_part)
        delp = QPushButton('删一块')
        delp.clicked.connect(self.delete_part)
        prow.addWidget(addp)
        prow.addWidget(delp)
        left.addLayout(prow)
        root.addLayout(left, 1)

        mid = QVBoxLayout()
        self.preview = Preview(self)
        mid.addWidget(self.preview, 1)
        opts = QHBoxLayout()
        opts.addWidget(QLabel('缩放'))
        self.zoom = QSpinBox()
        self.zoom.setRange(1, 8)
        self.zoom.setValue(4)
        self.zoom.valueChanged.connect(self.preview.update)
        self.onion = QCheckBox('洋葱皮')
        self.onion.stateChanged.connect(self.preview.update)
        self.flip = QCheckBox('水平翻转（朝向）')
        self.flip.stateChanged.connect(self.preview.update)
        self.play = QPushButton('播放')
        self.play.setCheckable(True)
        self.play.toggled.connect(self._toggle_play)
        opts.addWidget(self.zoom)
        opts.addWidget(self.onion)
        opts.addWidget(self.flip)
        opts.addWidget(self.play)
        mid.addLayout(opts)
        self.warn = QLabel('')
        self.warn.setWordWrap(True)
        mid.addWidget(self.warn)
        root.addLayout(mid, 2)

        right = QVBoxLayout()
        right.addWidget(QLabel('动画'))
        self.anims = QListWidget()
        self.anims.currentRowChanged.connect(self._anim_changed)
        right.addWidget(self.anims, 1)
        arow = QHBoxLayout()
        adda = QPushButton('新建动画')
        adda.clicked.connect(self.add_anim)
        dela = QPushButton('删除')
        dela.clicked.connect(self.delete_anim)
        arow.addWidget(adda)
        arow.addWidget(dela)
        right.addLayout(arow)
        self.anim_name = QLineEdit()
        self.anim_name.setPlaceholderText('动画名字')
        self.anim_name.editingFinished.connect(self._rename_anim)
        right.addWidget(self.anim_name)
        self.loop = QCheckBox('循环')
        self.loop.stateChanged.connect(self._apply_loop)
        right.addWidget(self.loop)
        right.addWidget(QLabel('帧'))
        self.frames = QListWidget()
        self.frames.currentRowChanged.connect(self._frame_changed)
        right.addWidget(self.frames, 1)
        frow = QHBoxLayout()
        addf = QPushButton('加一帧')
        addf.clicked.connect(self.add_frame)
        delf = QPushButton('删一帧')
        delf.clicked.connect(self.delete_frame)
        frow.addWidget(addf)
        frow.addWidget(delf)
        right.addLayout(frow)
        ff = QFormLayout()
        self.frame_meta = QComboBox()
        self.frame_dur = QSpinBox()
        self.frame_dur.setRange(1, 255)
        self.frame_meta.currentIndexChanged.connect(self._apply_frame)
        self.frame_dur.valueChanged.connect(self._apply_frame)
        ff.addRow('元精灵', self.frame_meta)
        ff.addRow('帧数', self.frame_dur)
        right.addLayout(ff)
        box = QGroupBox('实体的默认动画')
        dform = QFormLayout(box)
        self.defaults = QComboBox()
        self.default_type = QComboBox()
        self.default_type.currentIndexChanged.connect(self._show_default)
        self.defaults.currentIndexChanged.connect(self._apply_default)
        dform.addRow('实体', self.default_type)
        dform.addRow('动画', self.defaults)
        right.addWidget(box)
        check = QPushButton('检查编译')
        check.clicked.connect(self.check_compile)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumHeight(100)
        right.addWidget(check)
        right.addWidget(self.errors)
        root.addLayout(right, 1)

    def load(self, project):
        self.project = project
        self.doc = project.anims
        self._reload()
        self.errors.setPlainText('')

    def flush(self):
        self._apply_part()
        self._apply_frame()
        self._rename_meta()
        self._rename_anim()

    def refresh(self):
        if self.project:
            self.preview.update()

    def mark(self):
        if self.project:
            self.project.dirty['anims'] = True
            self.window.touch()

    def _reload(self):
        self._load = True
        self.metas.clear()
        for meta in self.doc.get('metas', []):
            self.metas.addItem(meta.get('label') or meta.get('name') or '未命名')
        self.anims.clear()
        for anim in self.doc.get('anims', []):
            self.anims.addItem(anim.get('label') or anim.get('name') or '未命名')
        self.default_type.clear()
        if self.project:
            for t in self.project.entity_spec.types:
                self.default_type.addItem(t.name, t.name)
        self._fill_meta_combo()
        self._load = False
        if self.metas.count():
            self.metas.setCurrentRow(0)
        if self.anims.count():
            self.anims.setCurrentRow(0)
        self._show_default()
        self._refresh_warn()
        self.preview.update()

    def _fill_meta_combo(self):
        cur = self.frame_meta.currentData()
        self.frame_meta.clear()
        self.defaults.clear()
        self.defaults.addItem('（无）', '')
        for meta in self.doc.get('metas', []):
            self.frame_meta.addItem(meta.get('name', ''), meta.get('name', ''))
        for anim in self.doc.get('anims', []):
            self.defaults.addItem(anim.get('name', ''), anim.get('name', ''))
        idx = self.frame_meta.findData(cur)
        if idx >= 0:
            self.frame_meta.setCurrentIndex(idx)

    def current_meta(self):
        row = self.metas.currentRow()
        metas = self.doc.get('metas', []) if self.doc else []
        if 0 <= row < len(metas):
            return metas[row]
        return None

    def current_anim(self):
        row = self.anims.currentRow()
        anims = self.doc.get('anims', []) if self.doc else []
        if 0 <= row < len(anims):
            return anims[row]
        return None

    def current_part(self):
        meta = self.current_meta()
        row = self.parts.currentRow()
        if not meta:
            return None
        parts = meta.get('parts') or []
        if 0 <= row < len(parts):
            return parts[row]
        return None

    def current_frame(self):
        anim = self.current_anim()
        row = self.frames.currentRow()
        if not anim:
            return None
        frames = anim.get('frames') or []
        if 0 <= row < len(frames):
            return frames[row]
        return None

    def add_meta(self):
        if self.doc is None:
            return
        n = len(self.doc.get('metas', [])) + 1
        self.doc.setdefault('metas', []).append(animc.new_meta('sprite%d' % n))
        self.mark()
        self._reload()
        self.metas.setCurrentRow(self.metas.count() - 1)

    def delete_meta(self):
        row = self.metas.currentRow()
        metas = self.doc.get('metas', []) if self.doc else []
        if 0 <= row < len(metas):
            del metas[row]
            self.mark()
            self._reload()

    def add_part(self):
        meta = self.current_meta()
        if not meta:
            return
        meta.setdefault('parts', []).append({'dx': 0, 'dy': 0, 'tile': 0, 'attr': 0})
        self.mark()
        self._meta_changed(self.metas.currentRow())
        self.parts.setCurrentRow(self.parts.count() - 1)

    def delete_part(self):
        meta = self.current_meta()
        row = self.parts.currentRow()
        if meta and 0 <= row < len(meta.get('parts') or []):
            del meta['parts'][row]
            self.mark()
            self._meta_changed(self.metas.currentRow())

    def add_anim(self):
        if self.doc is None:
            return
        n = len(self.doc.get('anims', [])) + 1
        anim = animc.new_anim('anim%d' % n)
        metas = self.doc.get('metas') or []
        if metas:
            anim['frames'][0]['meta'] = metas[0].get('name', '')
        self.doc.setdefault('anims', []).append(anim)
        self.mark()
        self._reload()
        self.anims.setCurrentRow(self.anims.count() - 1)

    def delete_anim(self):
        row = self.anims.currentRow()
        anims = self.doc.get('anims', []) if self.doc else []
        if 0 <= row < len(anims):
            del anims[row]
            self.mark()
            self._reload()

    def add_frame(self):
        anim = self.current_anim()
        if not anim:
            return
        meta = ''
        metas = self.doc.get('metas') or []
        if metas:
            meta = metas[0].get('name', '')
        anim.setdefault('frames', []).append({'meta': meta, 'dur': 8})
        self.mark()
        self._anim_changed(self.anims.currentRow())
        self.frames.setCurrentRow(self.frames.count() - 1)

    def delete_frame(self):
        anim = self.current_anim()
        row = self.frames.currentRow()
        if anim and 0 <= row < len(anim.get('frames') or []):
            del anim['frames'][row]
            self.mark()
            self._anim_changed(self.anims.currentRow())

    def _rename_meta(self):
        meta = self.current_meta()
        if not meta or self._load:
            return
        text = self.meta_name.text().strip()
        if not text or text == meta.get('name'):
            return
        if meta.get('label') in (None, '', meta.get('name')):
            meta['label'] = text
        meta['name'] = text
        self.mark()

    def _rename_anim(self):
        anim = self.current_anim()
        if not anim or self._load:
            return
        text = self.anim_name.text().strip()
        if not text or text == anim.get('name'):
            return
        if anim.get('label') in (None, '', anim.get('name')):
            anim['label'] = text
        anim['name'] = text
        self.mark()

    def _meta_changed(self, _row):
        meta = self.current_meta()
        self._load = True
        self.parts.clear()
        if meta:
            self.meta_name.setText(meta.get('name', ''))
            for part in meta.get('parts') or []:
                self.parts.addItem('(%s,%s) #%s 属性 %s' % (part.get('dx'), part.get('dy'), part.get('tile'), part.get('attr')))
            if self.parts.count():
                self.parts.setCurrentRow(0)
        self._load = False
        self._part_changed(self.parts.currentRow())
        self._refresh_warn()
        self.preview.update()

    def _part_changed(self, _row):
        part = self.current_part()
        self._load = True
        if part:
            self.dx.setValue(int(part.get('dx', 0) or 0))
            self.dy.setValue(int(part.get('dy', 0) or 0))
            self.tile.setValue(int(part.get('tile', 0) or 0))
            self.attr.setValue(int(part.get('attr', 0) or 0))
        self._load = False

    def _apply_part(self):
        part = self.current_part()
        if not part or self._load:
            return
        nxt = {
            'dx': self.dx.value(), 'dy': self.dy.value(),
            'tile': self.tile.value(), 'attr': self.attr.value(),
        }
        if all(part.get(k) == v for k, v in nxt.items()):
            return
        part.update(nxt)
        self.mark()
        self._refresh_warn()
        self.preview.update()

    def _anim_changed(self, _row):
        anim = self.current_anim()
        self._load = True
        self.frames.clear()
        self.frame_i = 0
        if anim:
            self.anim_name.setText(anim.get('name', ''))
            self.loop.setChecked(bool(anim.get('loop', True)))
            for frame in anim.get('frames') or []:
                self.frames.addItem('%s  × %s 帧' % (frame.get('meta'), frame.get('dur')))
            if self.frames.count():
                self.frames.setCurrentRow(0)
        self._load = False
        self._frame_changed(self.frames.currentRow())
        self.preview.update()

    def _frame_changed(self, row):
        frame = self.current_frame()
        self._load = True
        if frame:
            self.frame_i = row if row >= 0 else 0
            idx = self.frame_meta.findData(frame.get('meta', ''))
            if idx >= 0:
                self.frame_meta.setCurrentIndex(idx)
            self.frame_dur.setValue(int(frame.get('dur', 1) or 1))
        self._load = False
        self.preview.update()

    def _apply_frame(self):
        frame = self.current_frame()
        if not frame or self._load:
            return
        meta = self.frame_meta.currentData() or ''
        dur = self.frame_dur.value()
        if frame.get('meta') == meta and frame.get('dur') == dur:
            return
        frame['meta'] = meta
        frame['dur'] = dur
        self.mark()
        self.preview.update()

    def _apply_loop(self):
        anim = self.current_anim()
        if not anim or self._load:
            return
        looping = self.loop.isChecked()
        if bool(anim.get('loop', True)) == looping:
            return
        anim['loop'] = looping
        self.mark()

    def _show_default(self):
        if self._load or not self.doc:
            return
        name = self.default_type.currentData()
        anim = (self.doc.get('defaults') or {}).get(name, '')
        self._load = True
        idx = self.defaults.findData(anim)
        self.defaults.setCurrentIndex(idx if idx >= 0 else 0)
        self._load = False

    def _apply_default(self):
        if self._load or not self.doc:
            return
        name = self.default_type.currentData()
        if not name:
            return
        defaults = self.doc.setdefault('defaults', {})
        anim = self.defaults.currentData() or ''
        if anim:
            if defaults.get(name) == anim:
                return
            defaults[name] = anim
        elif name in defaults:
            del defaults[name]
        else:
            return
        self.mark()

    def _meta_by_name(self, name):
        for meta in self.doc.get('metas', []) if self.doc else []:
            if meta.get('name') == name:
                return meta
        return None

    def preview_parts(self):
        anim = self.current_anim()
        if anim and anim.get('frames'):
            frames = anim['frames']
            idx = self.frame_i % len(frames)
            meta = self._meta_by_name(frames[idx].get('meta'))
            if meta:
                return meta.get('parts') or []
        meta = self.current_meta()
        return (meta.get('parts') if meta else None) or []

    def onion_parts(self):
        anim = self.current_anim()
        if not anim or len(anim.get('frames') or []) < 2:
            return None
        frames = anim['frames']
        idx = (self.frame_i - 1) % len(frames)
        meta = self._meta_by_name(frames[idx].get('meta'))
        if not meta:
            return None
        return meta.get('parts') or []

    def _refresh_warn(self):
        meta = self.current_meta()
        if not meta:
            self.warn.setText('')
            return
        msgs = animc.frame_warnings(meta.get('parts') or [])
        self.warn.setText('；'.join(msgs) if msgs else '这一帧的精灵数量在 64 个、每行 8 个以内。')

    def _toggle_play(self, on):
        if on:
            self.play_timer.start(80)
            self.play.setText('停止')
        else:
            self.play_timer.stop()
            self.play.setText('播放')

    def _tick(self):
        anim = self.current_anim()
        if not anim or not anim.get('frames'):
            return
        n = len(anim['frames'])
        nxt = self.frame_i + 1
        if nxt >= n:
            if anim.get('loop', True):
                nxt = 0
            else:
                nxt = n - 1
                self.play.setChecked(False)
        self.frame_i = nxt
        self.frames.setCurrentRow(self.frame_i)
        self.preview.update()

    def check_compile(self):
        if not self.doc:
            return []
        self.flush()
        errors = animc.check(self.doc)
        if errors:
            self.errors.setPlainText('\n'.join(errors))
        else:
            self.errors.setPlainText('动画检查通过（%d 个元精灵，%d 个动画）' % (
                len(self.doc.get('metas') or []), len(self.doc.get('anims') or [])))
        return errors
