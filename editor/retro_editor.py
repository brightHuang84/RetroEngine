#!/usr/bin/env python3
"""RetroEngine 编辑器：图块、调色板、地图、音乐，以及编译运行。

  python3 editor/retro_editor.py
  python3 editor/retro_editor.py games/breakout
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PySide6.QtCore import Qt, QProcess, QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import (
        QFont, QColor, QImage, QPainter, QPen, QIcon, QSyntaxHighlighter, QTextCharFormat,
    )
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QScrollArea, QComboBox, QSpinBox, QCheckBox, QPlainTextEdit,
        QListWidget, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox, QInputDialog,
        QDialog, QDialogButtonBox, QLineEdit, QGroupBox, QRadioButton, QButtonGroup,
        QStatusBar,
    )
except ImportError:
    sys.stderr.write('缺少 PySide6。\n')
    sys.stderr.write('Ubuntu 26.04：sudo apt install python3-pyside6 python3-pyside6.qtmultimedia\n')
    sys.stderr.write('或：python3 -m pip install --user PySide6\n')
    sys.exit(1)

import re_data as data
import re_synth
import re_build

APP_FONT = 'WenQuanYi Micro Hei'


class Hist(object):
    def __init__(self):
        self.undo = []
        self.redo = []

    def push(self, state):
        self.undo.append(state)
        self.redo.clear()
        if len(self.undo) > 40:
            del self.undo[0]

    def undo(self, current):
        if not self.undo:
            return None
        self.redo.append(current)
        return self.undo.pop()

    def redo(self, current):
        if not self.redo:
            return None
        self.undo.append(current)
        return self.redo.pop()


class CHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        QSyntaxHighlighter.__init__(self, doc)
        self.rules = []
        kw = QTextCharFormat()
        kw.setForeground(QColor('#7ec8ff'))
        for word in ('static', 'const', 'void', 'if', 'else', 'for', 'while', 'return',
                     'include', 'define', 'u8', 'u16', 's8', 's16'):
            self.rules.append((re_compile(r'\b%s\b' % word), kw))
        s = QTextCharFormat()
        s.setForeground(QColor('#c3e88d'))
        self.rules.append((re_compile(r'"[^"]*"'), s))
        c = QTextCharFormat()
        c.setForeground(QColor('#6a9955'))
        self.rules.append((re_compile(r'//.*'), c))
        self.comment = c

    def highlightBlock(self, text):
        for rx, fmt in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def re_compile(pat):
    import re
    return re.compile(pat)


def fill_rect(img, x, y, w, h, rgb):
    color = 0xFF000000 | (rgb & 0xFFFFFF)
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= xx < img.width() and 0 <= yy < img.height():
                img.setPixel(xx, yy, color)


def tile_image(tiles, index, palette, scale, backdrop=None):
    """Four colors of one NES palette. Color 0 is that palette's own color 0
    unless backdrop is set, in which case color 0 uses the shared backdrop."""
    img = QImage(8 * scale, 8 * scale, QImage.Format_RGB32)
    colors = []
    for i in range(4):
        if i == 0 and backdrop is not None:
            colors.append(data.rgb_of(backdrop))
        else:
            colors.append(data.rgb_of(palette[i]))
    for y in range(8):
        for x in range(8):
            fill_rect(img, x * scale, y * scale, scale, scale, colors[tiles.tile_get(index, x, y)])
    return img


def sheet_image(tiles, palette, cell, backdrop=None):
    img = QImage(16 * cell, 16 * cell, QImage.Format_RGB32)
    img.fill(QColor('#111111'))
    painter = QPainter(img)
    scale = max(1, (cell - 1) // 8)
    for i in range(min(256, tiles.count())):
        sub = tile_image(tiles, i, palette, scale, backdrop)
        painter.drawImage((i % 16) * cell + 1, (i // 16) * cell + 1, sub)
    painter.end()
    return img


def map_image(project, game_map, scale, grid=True, screens=True, conflicts=True):
    w, h = game_map.w, game_map.h
    attrs = data.attribute_bytes(w, h, game_map.effective_pal)
    img = QImage(max(1, w * 8 * scale), max(1, h * 8 * scale), QImage.Format_RGB32)
    pal = project.palette
    backdrop = pal[0]
    for ty in range(h):
        for tx in range(w):
            tile = game_map.tile_at(tx, ty)
            p = data.resolved_palette(tx, ty, attrs)
            group = pal[p * 4:p * 4 + 4]
            for py in range(8):
                for px in range(8):
                    v = project.tiles.tile_get(tile, px, py)
                    rgb = data.rgb_of(backdrop if v == 0 else group[v])
                    fill_rect(img, (tx * 8 + px) * scale, (ty * 8 + py) * scale, scale, scale, rgb)
    painter = QPainter(img)
    if grid:
        painter.setPen(QPen(QColor(255, 255, 255, 50)))
        step = 16 * scale
        for x in range(0, img.width(), step):
            painter.drawLine(x, 0, x, img.height())
        for y in range(0, img.height(), step):
            painter.drawLine(0, y, img.width(), y)
    if screens:
        painter.setPen(QPen(QColor('#ffd24a'), 2))
        for col in (32, 64):
            x = col * 8 * scale
            if x < img.width():
                painter.drawLine(x, 0, x, img.height())
    if conflicts:
        painter.setPen(QPen(QColor('#ff4040'), 2))
        for x, y, _pals in data.attribute_conflicts(w, h, game_map.effective_pal):
            painter.drawRect(x * 8 * scale, y * 8 * scale, 16 * scale - 1, 16 * scale - 1)
    painter.end()
    return img


class TileCanvas(QWidget):
    def __init__(self, tab):
        QWidget.__init__(self)
        self.tab = tab
        self.scale = 28
        self.setFixedSize(8 * self.scale + 1, 8 * self.scale + 1)
        self.setMouseTracking(True)

    def paintEvent(self, _e):
        p = QPainter(self)
        if not self.tab.project:
            return
        img = tile_image(self.tab.project.tiles, self.tab.index, self.tab.preview_colors(), self.scale)
        p.drawImage(0, 0, img)
        p.setPen(QColor('#888888'))
        for i in range(9):
            p.drawLine(i * self.scale, 0, i * self.scale, 8 * self.scale)
            p.drawLine(0, i * self.scale, 8 * self.scale, i * self.scale)

    def _cell(self, event):
        pos = event.position()
        return int(pos.x()) // self.scale, int(pos.y()) // self.scale

    def mousePressEvent(self, event):
        x, y = self._cell(event)
        if event.button() == Qt.RightButton:
            if self.tab.project:
                self.tab.pen = self.tab.project.tiles.tile_get(self.tab.index, x, y)
                self.tab.sync_pen_buttons()
            return
        if event.button() == Qt.LeftButton:
            self.tab.begin_stroke()
            self.tab.paint_pixel(x, y)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            x, y = self._cell(event)
            self.tab.paint_pixel(x, y)

    def mouseReleaseEvent(self, event):
        self.tab._stroke = False
        QWidget.mouseReleaseEvent(self, event)


class TileTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.project = None
        self.index = 0
        self.pen = 1
        self.pal_index = 0
        self.clip = None
        self.hist = Hist()
        self._stroke = False
        self.canvas = TileCanvas(self)
        self.picker = QLabel()
        self.picker.setMouseTracking(True)
        self.picker.mousePressEvent = self._pick
        self.info = QLabel('图块 00')
        self.pal_box = QComboBox()
        for name in data.PAL_NAMES:
            self.pal_box.addItem(name)
        self.pal_box.currentIndexChanged.connect(self._pal_changed)
        pens = QHBoxLayout()
        self.pen_buttons = []
        for i, label in enumerate(('色 0', '色 1', '色 2', '色 3')):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, n=i: self._set_pen(n))
            self.pen_buttons.append(b)
            pens.addWidget(b)
        root = QHBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidget(self.picker)
        scroll.setWidgetResizable(False)
        scroll.setMinimumWidth(320)
        root.addWidget(scroll, 1)
        right = QVBoxLayout()
        right.addWidget(self.info)
        right.addWidget(self.canvas, 0, Qt.AlignLeft)
        right.addLayout(pens)
        right.addWidget(QLabel('预览用的调色板'))
        right.addWidget(self.pal_box)
        row = QHBoxLayout()
        for text, slot in (('复制', self.copy_tile), ('粘贴', self.paste_tile),
                           ('水平翻转', self.flip_h), ('垂直翻转', self.flip_v)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        right.addLayout(row)
        right.addWidget(QLabel('左键涂色，右键取色。色 0 在背景里是透明的，游戏用背景色。'))
        right.addStretch(1)
        root.addLayout(right, 1)

    def load(self, project):
        self.project = project
        self.hist = Hist()
        self.index = 0
        self.refresh()

    def preview_colors(self):
        if not self.project:
            return [0x0F, 0x00, 0x10, 0x30]
        i = self.pal_index * 4
        return self.project.palette[i:i + 4]

    def refresh(self):
        if not self.project:
            return
        self.picker.setPixmap(QPixmap_from(sheet_image(self.project.tiles, self.preview_colors(), 18)))
        self.picker.resize(self.picker.pixmap().size())
        self.info.setText('图块 $%02X（第 %d 号）  笔：色 %d' % (self.index, self.index, self.pen))
        self.sync_pen_buttons()
        self.canvas.update()

    def sync_pen_buttons(self):
        colors = self.preview_colors()
        for i, b in enumerate(self.pen_buttons):
            rgb = data.rgb_of(colors[i])
            mark = ' ▶' if i == self.pen else ''
            b.setText('色 %d%s' % (i, mark))
            b.setStyleSheet('background:#%06X; color:%s;' % (rgb, '#000' if (rgb & 0xFF) > 0x80 else '#fff'))

    def _set_pen(self, n):
        self.pen = n
        self.refresh()

    def _pal_changed(self, idx):
        self.pal_index = idx
        self.refresh()

    def _pick(self, event):
        cell = 18
        x = int(event.position().x()) // cell
        y = int(event.position().y()) // cell
        if 0 <= x < 16 and 0 <= y < 16:
            self.select_tile(y * 16 + x)

    def select_tile(self, index):
        self.index = index & 255
        self.refresh()

    def begin_stroke(self):
        if self._stroke or not self.project:
            return
        self.hist.push(bytearray(self.project.tiles.pixels))
        self._stroke = True

    def mouseReleaseEvent(self, event):
        self._stroke = False
        QWidget.mouseReleaseEvent(self, event)

    def paint_pixel(self, x, y):
        if not self.project or not (0 <= x < 8 and 0 <= y < 8):
            return
        self.project.tiles.tile_set(self.index, x, y, self.pen)
        self.project.dirty['tiles'] = True
        self.canvas.update()
        self.window.touch()

    def _restore(self, pixels):
        self.project.tiles.pixels[:] = pixels
        self.project.dirty['tiles'] = True
        self.refresh()

    def undo(self):
        if not self.project:
            return
        prev = self.hist.undo(bytearray(self.project.tiles.pixels))
        if prev is not None:
            self._restore(prev)

    def redo(self):
        if not self.project:
            return
        nxt = self.hist.redo(bytearray(self.project.tiles.pixels))
        if nxt is not None:
            self._restore(nxt)

    def copy_tile(self):
        if self.project:
            self.clip = self.project.tiles.tile_grid(self.index)

    def paste_tile(self):
        if self.project and self.clip:
            self.begin_stroke()
            self._stroke = False
            self.project.tiles.tile_paste(self.index, self.clip)
            self.project.dirty['tiles'] = True
            self.refresh()

    def flip_h(self):
        self._flip(True)

    def flip_v(self):
        self._flip(False)

    def _flip(self, horizontal):
        if not self.project:
            return
        self.begin_stroke()
        self._stroke = False
        grid = self.project.tiles.tile_grid(self.index)
        out = [0] * 64
        for y in range(8):
            for x in range(8):
                sx = 7 - x if horizontal else x
                sy = y if horizontal else 7 - y
                out[y * 8 + x] = grid[sy * 8 + sx]
        self.project.tiles.tile_paste(self.index, out)
        self.project.dirty['tiles'] = True
        self.refresh()


class PaletteTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.project = None
        self.slot = 0
        self.hist = Hist()
        root = QVBoxLayout(self)
        root.addWidget(QLabel('上面 32 格是游戏的调色板。点一格，再点下面的 NES 64 色。背景色 0 全屏共用第 1 格。'))
        self.grid = QGridLayout()
        self.slots = []
        for i in range(32):
            b = QPushButton()
            b.setFixedSize(48, 36)
            b.clicked.connect(lambda _c=False, n=i: self._select(n))
            self.slots.append(b)
            self.grid.addWidget(b, i // 4, i % 4)
            if i % 4 == 0:
                self.grid.addWidget(QLabel(data.PAL_NAMES[i // 4]), i // 4, 4)
        wrap = QWidget()
        wrap.setLayout(self.grid)
        root.addWidget(wrap)
        root.addWidget(QLabel('NES 64 色'))
        nes = QGridLayout()
        self.nes_buttons = []
        for i in range(64):
            b = QPushButton('%02X' % i)
            b.setFixedSize(40, 28)
            rgb = data.rgb_of(i)
            b.setStyleSheet('background:#%06X; color:%s; font-size:10px;' % (
                rgb, '#000' if (rgb & 0xFF) > 0xA0 else '#fff'))
            b.clicked.connect(lambda _c=False, n=i: self.assign(n))
            self.nes_buttons.append(b)
            nes.addWidget(b, i // 16, i % 16)
        box = QWidget()
        box.setLayout(nes)
        root.addWidget(box)
        root.addStretch(1)

    def load(self, project):
        self.project = project
        self.hist = Hist()
        self.refresh()

    def refresh(self):
        if not self.project:
            return
        for i, b in enumerate(self.slots):
            rgb = data.rgb_of(self.project.palette[i])
            border = '#ffd24a' if i == self.slot else '#444'
            b.setText('%02X' % self.project.palette[i])
            b.setStyleSheet('background:#%06X; color:%s; border:2px solid %s;' % (
                rgb, '#000' if (rgb & 0xFF) > 0xA0 else '#fff', border))

    def _select(self, index):
        self.slot = index
        self.refresh()

    def assign(self, nes_index):
        if not self.project:
            return
        self.hist.push(list(self.project.palette))
        self.project.palette[self.slot] = nes_index & 63
        self.project.dirty['palette'] = True
        self.refresh()
        self.window.tile_tab.refresh()
        self.window.touch()

    def set_color(self, slot, nes_index):
        self.slot = slot
        self.assign(nes_index)

    def undo(self):
        if not self.project:
            return
        prev = self.hist.undo(list(self.project.palette))
        if prev is not None:
            self.project.palette[:] = prev
            self.project.dirty['palette'] = True
            self.refresh()
            self.window.tile_tab.refresh()

    def redo(self):
        if not self.project:
            return
        nxt = self.hist.redo(list(self.project.palette))
        if nxt is not None:
            self.project.palette[:] = nxt
            self.project.dirty['palette'] = True
            self.refresh()
            self.window.tile_tab.refresh()


class MapView(QLabel):
    def __init__(self, tab):
        QLabel.__init__(self)
        self.tab = tab
        self.setMouseTracking(True)

    def _cell(self, event):
        scale = self.tab.scale
        return int(event.position().x()) // (8 * scale), int(event.position().y()) // (8 * scale)

    def mousePressEvent(self, event):
        x, y = self._cell(event)
        if event.button() == Qt.RightButton:
            self.tab.sample(x, y)
            return
        if event.button() == Qt.LeftButton:
            self.tab.begin_stroke()
            self.tab.paint_cell(x, y)

    def mouseMoveEvent(self, event):
        x, y = self._cell(event)
        self.tab.hover(x, y)
        if event.buttons() & Qt.LeftButton:
            self.tab.paint_cell(x, y)

    def mouseReleaseEvent(self, event):
        self.tab._stroke = False
        QLabel.mouseReleaseEvent(self, event)


class MapTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.project = None
        self.scale = 2
        self.tile = 0x20
        self.pal = 0
        self.hist = Hist()
        self._stroke = False
        root = QHBoxLayout(self)
        side = QVBoxLayout()
        self.map_box = QComboBox()
        self.map_box.currentIndexChanged.connect(self._map_changed)
        side.addWidget(QLabel('地图'))
        side.addWidget(self.map_box)
        self.picker = QLabel()
        self.picker.mousePressEvent = self._pick_tile
        scroll_p = QScrollArea()
        scroll_p.setWidget(self.picker)
        scroll_p.setMinimumWidth(250)
        scroll_p.setMaximumWidth(280)
        side.addWidget(scroll_p, 1)
        self.pal_group = QButtonGroup(self)
        for i in range(4):
            rb = QRadioButton('背景调色板 %d' % i)
            self.pal_group.addButton(rb, i)
            side.addWidget(rb)
        self.pal_group.button(0).setChecked(True)
        self.pal_group.idClicked.connect(self._set_pal)
        self.solid = QCheckBox('实心（这一种图块共用）')
        self.solid.toggled.connect(self._solid)
        side.addWidget(self.solid)
        self.auto = QCheckBox('画的时候统一 16×16 调色板')
        self.auto.setChecked(True)
        side.addWidget(self.auto)
        self.grid = QCheckBox('显示 16×16 网格和屏幕分界')
        self.grid.setChecked(True)
        self.grid.toggled.connect(lambda _v: self.refresh())
        side.addWidget(self.grid)
        zoom = QHBoxLayout()
        zoom.addWidget(QLabel('缩放'))
        self.zoom = QSpinBox()
        self.zoom.setRange(1, 4)
        self.zoom.setValue(2)
        self.zoom.valueChanged.connect(self._zoom)
        zoom.addWidget(self.zoom)
        side.addLayout(zoom)
        self.hover_label = QLabel(' ')
        self.hover_label.setWordWrap(True)
        side.addWidget(self.hover_label)
        root.addLayout(side)
        self.view = MapView(self)
        sc = QScrollArea()
        sc.setWidget(self.view)
        root.addWidget(sc, 1)

    def load(self, project):
        self.project = project
        self.hist = Hist()
        self.map_box.blockSignals(True)
        self.map_box.clear()
        for m in project.maps:
            self.map_box.addItem('%s  (%d×%d)' % (m.name, m.w, m.h), m.name)
        self.map_box.blockSignals(False)
        self.refresh()

    def current(self):
        if not self.project or not self.project.maps:
            return None
        name = self.map_box.currentData()
        return self.project.map_by_name(name)

    def _map_changed(self, _i):
        self.refresh()

    def _zoom(self, value):
        self.scale = value
        self.refresh()

    def _set_pal(self, idx):
        self.pal = idx

    def _pick_tile(self, event):
        cell = 16
        x = int(event.position().x()) // cell
        y = int(event.position().y()) // cell
        if 0 <= x < 16 and 0 <= y < 16:
            self.select_tile(y * 16 + x)

    def select_tile(self, index):
        self.tile = index & 255
        m = self.current()
        if m:
            self.solid.blockSignals(True)
            self.solid.setChecked(m.solid_of(self.tile))
            self.solid.blockSignals(False)
        self.refresh()

    def _solid(self, checked):
        m = self.current()
        if not m:
            return
        self.begin_stroke()
        self._stroke = False
        m.set_solid(self.tile, checked)
        self.project.dirty['maps'] = True
        self.refresh()

    def begin_stroke(self):
        m = self.current()
        if self._stroke or not m:
            return
        self.hist.push(m.copy_state())
        self._stroke = True

    def mouseReleaseEvent(self, event):
        self._stroke = False
        QWidget.mouseReleaseEvent(self, event)

    def paint_cell(self, x, y):
        m = self.current()
        if not m or not (0 <= x < m.w and 0 <= y < m.h):
            return
        m.paint(x, y, self.tile, self.pal, self.auto.isChecked())
        self.project.dirty['maps'] = True
        self.refresh()
        self.window.touch()

    def sample(self, x, y):
        m = self.current()
        if not m or not (0 <= x < m.w and 0 <= y < m.h):
            return
        self.select_tile(m.tile_at(x, y))
        self.pal = m.effective_pal(x, y)
        btn = self.pal_group.button(self.pal)
        if btn:
            btn.setChecked(True)

    def hover(self, x, y):
        m = self.current()
        if not m or not (0 <= x < m.w and 0 <= y < m.h):
            return
        attrs = data.attribute_bytes(m.w, m.h, m.effective_pal)
        got = data.resolved_palette(x, y, attrs)
        self.hover_label.setText(
            '坐标 (%d,%d)  图块 $%02X  格子调色板 %d  属性块实际 %d%s' % (
                x, y, m.tile_at(x, y), m.effective_pal(x, y), got,
                '  实心' if m.solid_of(m.tile_at(x, y)) else ''))

    def refresh(self):
        if not self.project:
            return
        group = self.project.palette[self.pal * 4:self.pal * 4 + 4]
        self.picker.setPixmap(QPixmap_from(sheet_image(self.project.tiles, group, 16, self.project.palette[0])))
        self.picker.resize(self.picker.pixmap().size())
        m = self.current()
        if not m:
            return
        img = map_image(self.project, m, self.scale, self.grid.isChecked(), self.grid.isChecked(), True)
        self.view.setPixmap(QPixmap_from(img))
        self.view.resize(img.size())
        conf = data.attribute_conflicts(m.w, m.h, m.effective_pal)
        if conf:
            x, y, pals = conf[0]
            extra = '，例如 (%d,%d) 调色板 %s' % (x, y, ' 和 '.join(str(p) for p in pals))
            self.hover_label.setText('属性块冲突 %d 处%s。引擎采用该块里第一个非 0 调色板。' % (len(conf), extra))
        else:
            self.hover_label.setText('黄线是第 32 列的屏幕分界。左键涂格子，右键取图块。')
        self.window.touch()

    def undo(self):
        m = self.current()
        if not m:
            return
        prev = self.hist.undo(m.copy_state())
        if prev is not None:
            m.restore_state(prev)
            self.project.dirty['maps'] = True
            self.refresh()

    def redo(self):
        m = self.current()
        if not m:
            return
        nxt = self.hist.redo(m.copy_state())
        if nxt is not None:
            m.restore_state(nxt)
            self.project.dirty['maps'] = True
            self.refresh()


def QPixmap_from(image):
    from PySide6.QtGui import QPixmap
    return QPixmap.fromImage(image)


class MusicTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.project = None
        self.player = AudioPlayer()
        self._load_lock = False
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.songs = QListWidget()
        self.songs.currentRowChanged.connect(self._song_changed)
        left.addWidget(QLabel('歌曲'))
        left.addWidget(self.songs, 1)
        for text, slot in (('新建', self.new_song), ('删除', self.delete_song),
                           ('导入 FamiStudio 文本', self.import_fms)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            left.addWidget(b)
        root.addLayout(left, 0)
        right = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(QLabel('速度'))
        self.tempo = QSpinBox()
        self.tempo.setRange(30, 300)
        self.tempo.valueChanged.connect(self._tempo)
        head.addWidget(self.tempo)
        self.chan = QComboBox()
        for label in data.CHAN_LABELS:
            self.chan.addItem(label)
        self.chan.currentIndexChanged.connect(lambda _i: self.reload_table())
        head.addWidget(self.chan)
        head.addWidget(QLabel('占空/模式'))
        self.duty = QSpinBox()
        self.duty.setRange(0, 3)
        self.duty.valueChanged.connect(self._duty)
        head.addWidget(self.duty)
        head.addWidget(QLabel('音量'))
        self.vol = QSpinBox()
        self.vol.setRange(0, 15)
        self.vol.valueChanged.connect(self._vol)
        head.addWidget(self.vol)
        self.once = QCheckBox('只播一次')
        self.once.toggled.connect(self._once)
        head.addWidget(self.once)
        right.addLayout(head)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['音符', '时值'])
        self.table.itemChanged.connect(self._item)
        right.addWidget(self.table, 1)
        keys = QHBoxLayout()
        self.octave = QSpinBox()
        self.octave.setRange(1, 7)
        self.octave.setValue(4)
        keys.addWidget(QLabel('八度'))
        keys.addWidget(self.octave)
        for name in data.NOTE_NAMES:
            b = QPushButton(name)
            b.clicked.connect(lambda _c=False, n=name: self._type_note(n))
            keys.addWidget(b)
        rest = QPushButton('休止')
        rest.clicked.connect(lambda: self._type_note('R'))
        keys.addWidget(rest)
        right.addLayout(keys)
        ops = QHBoxLayout()
        for text, slot in (('加一行', self.add_row), ('删除行', self.del_row),
                           ('从此循环', self.set_loop), ('整首循环', self.clear_loop),
                           ('播放', self.play), ('停止', self.stop)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            ops.addWidget(b)
        right.addLayout(ops)
        sfx = QHBoxLayout()
        sfx.addWidget(QLabel('音效'))
        for i, name in enumerate(re_synth.SFX_NAMES):
            if not name:
                continue
            b = QPushButton(name)
            b.clicked.connect(lambda _c=False, n=i: self.play_sfx(n))
            sfx.addWidget(b)
        right.addLayout(sfx)
        self.length_label = QLabel(' ')
        right.addWidget(self.length_label)
        right.addWidget(QLabel('时值用 1 2 4 8 16 32，附点写成 8. ，或 t12 表示 12 帧。噪声用 N0–N15。'))
        root.addLayout(right, 1)

    def load(self, project):
        self.project = project
        self.songs.clear()
        for s in project.songs:
            self.songs.addItem(s.name)
        if project.songs:
            self.songs.setCurrentRow(0)
        else:
            self.reload_table()

    def song(self):
        if not self.project or self.songs.currentRow() < 0:
            return None
        row = self.songs.currentRow()
        if row >= len(self.project.songs):
            return None
        return self.project.songs[row]

    def channel(self):
        song = self.song()
        if not song:
            return None
        idx = self.chan.currentIndex()
        if song.ch[idx] is None:
            song.ch[idx] = data.Channel()
            if idx == 3:
                song.ch[idx].duty = 0
                song.ch[idx].vol = 6
            elif idx == 2:
                song.ch[idx].vol = 15
        return song.ch[idx]

    def _song_changed(self, _row):
        song = self.song()
        if not song:
            return
        self.tempo.blockSignals(True)
        self.tempo.setValue(song.tempo)
        self.tempo.blockSignals(False)
        self.reload_table()

    def reload_table(self):
        self._load_lock = True
        ch = self.channel()
        song = self.song()
        self.table.setRowCount(0)
        if ch is None:
            self._load_lock = False
            return
        self.duty.blockSignals(True)
        self.vol.blockSignals(True)
        self.once.blockSignals(True)
        self.duty.setValue(ch.duty)
        self.vol.setValue(ch.vol)
        self.once.setChecked(ch.once)
        self.duty.blockSignals(False)
        self.vol.blockSignals(False)
        self.once.blockSignals(False)
        self.table.setRowCount(len(ch.events))
        for i, (note, dur) in enumerate(ch.events):
            mark = note
            if ch.loop_at not in (None, 0) and i == ch.loop_at:
                mark = '↻ ' + note
            self.table.setItem(i, 0, QTableWidgetItem(mark.replace('↻ ', '')))
            self.table.setItem(i, 1, QTableWidgetItem(dur))
            if ch.loop_at not in (None, 0) and i == ch.loop_at:
                self.table.item(i, 0).setBackground(QColor('#3d4f2f'))
        self._load_lock = False
        self._lengths(song)

    def _lengths(self, song):
        if not song:
            return
        try:
            compiled = data.song_frames(song)
        except (SystemExit, Exception) as exc:
            self.length_label.setText('还不能播放：%s' % exc)
            return
        bits = []
        for i, ch in enumerate(compiled.ch):
            n = 0 if ch is None else sum(d for _p, d in ch.events)
            bits.append('%s %d 帧' % (data.CHAN_LABELS[i], n))
        self.length_label.setText('  '.join(bits) + '    各通道帧数不同会慢慢错开。')

    def _touch(self):
        if self.project:
            self.project.dirty['songs'] = True
            self.window.touch()

    def _tempo(self, value):
        song = self.song()
        if song and not self._load_lock:
            song.tempo = value
            self._touch()
            self._lengths(song)

    def _duty(self, value):
        ch = self.channel()
        if ch and not self._load_lock:
            ch.duty = value
            self._touch()

    def _vol(self, value):
        ch = self.channel()
        if ch and not self._load_lock:
            ch.vol = value
            self._touch()

    def _once(self, checked):
        ch = self.channel()
        if ch and not self._load_lock:
            ch.once = bool(checked)
            self._touch()

    def _item(self, item):
        if self._load_lock:
            return
        ch = self.channel()
        if not ch or item.row() >= len(ch.events):
            return
        note, dur = ch.events[item.row()]
        text = item.text().strip()
        if item.column() == 0:
            note = text
        else:
            dur = text
        ch.events[item.row()] = (note, dur)
        self._touch()
        self._lengths(self.song())

    def _type_note(self, name):
        ch = self.channel()
        if not ch:
            return
        if self.chan.currentIndex() == 3 and name != 'R':
            name = 'N%d' % data.NOTE_NAMES.index(name)
        elif name not in ('R',) and self.chan.currentIndex() != 3:
            name = name + str(self.octave.value())
        row = self.table.currentRow()
        if row < 0:
            self.add_row()
            row = self.table.rowCount() - 1
        note, dur = ch.events[row]
        ch.events[row] = (name, dur)
        self.reload_table()
        self.table.setCurrentCell(row, 0)
        self._touch()

    def add_row(self):
        ch = self.channel()
        if not ch:
            return
        token = 'N1' if self.chan.currentIndex() == 3 else 'C4'
        ch.events.append((token, '8'))
        self.reload_table()
        self._touch()

    def del_row(self):
        ch = self.channel()
        row = self.table.currentRow()
        if not ch or row < 0 or row >= len(ch.events):
            return
        del ch.events[row]
        if ch.loop_at is not None and ch.loop_at > row:
            ch.loop_at -= 1
        self.reload_table()
        self._touch()

    def set_loop(self):
        ch = self.channel()
        row = self.table.currentRow()
        if not ch or row < 0:
            return
        ch.loop_at = row
        self.reload_table()
        self._touch()

    def clear_loop(self):
        ch = self.channel()
        if not ch:
            return
        ch.loop_at = None
        self.reload_table()
        self._touch()

    def play(self):
        song = self.song()
        if not song:
            return
        try:
            compiled = data.song_frames(song)
            samples = re_synth.render_song(compiled, seconds=6)
        except (SystemExit, Exception) as exc:
            QMessageBox.warning(self, '播放', '这首曲子还不能编译：\n%s' % exc)
            return
        self.player.play(samples)

    def play_sfx(self, sfx_id):
        self.player.play(re_synth.render_sfx(sfx_id))

    def stop(self):
        self.player.stop()

    def new_song(self):
        if not self.project:
            return
        name, ok = QInputDialog.getText(self, '新建歌曲', '歌曲名（字母数字）：')
        if not ok or not name.strip():
            return
        song = data.Song(name.strip())
        ch = data.Channel()
        ch.events = [('C4', '4'), ('E4', '4'), ('G4', '4'), ('C5', '4')]
        song.ch[0] = ch
        self.project.songs.append(song)
        self.songs.addItem(song.name)
        self.songs.setCurrentRow(self.songs.count() - 1)
        self._touch()

    def delete_song(self):
        row = self.songs.currentRow()
        if not self.project or row < 0:
            return
        del self.project.songs[row]
        self.load(self.project)
        self._touch()

    def import_fms(self):
        if not self.project:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'FamiStudio 文本', self.project.root, '文本 (*.txt *.fms.txt)')
        if not path:
            return
        import subprocess
        import tempfile
        fd, out = tempfile.mkstemp(suffix='.txt')
        os.close(fd)
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO, 'tools', 'fms2mus.py'), '--out', out, path],
            capture_output=True, text=True)
        text = open(out).read()
        os.remove(out)
        if proc.returncode != 0:
            QMessageBox.warning(self, '导入', proc.stderr or '导入失败')
            return
        songs = data.parse_songs(text)
        if not songs:
            QMessageBox.warning(self, '导入', '文件里没有曲子。\n' + proc.stderr)
            return
        self.project.songs.extend(songs)
        self.load(self.project)
        self.songs.setCurrentRow(len(self.project.songs) - 1)
        self._touch()
        if proc.stderr.strip():
            QMessageBox.information(self, '导入', '已加入 %d 首。这些内容被忽略：\n%s' % (len(songs), proc.stderr.strip()))

    def undo(self):
        pass

    def redo(self):
        pass


class AudioPlayer(object):
    def __init__(self):
        self.sink = None
        self.buf = None
        self._proc = None

    def play(self, samples):
        self.stop()
        # Qt's multimedia backend segfaults when it sees a device but PipeWire
        # has no session socket (typical of a headless shell). Use it only when
        # a real audio session is there; otherwise hand the samples to aplay.
        runtime = os.environ.get('XDG_RUNTIME_DIR', '')
        session = runtime and (
            os.path.exists(os.path.join(runtime, 'pulse', 'native'))
            or os.path.exists(os.path.join(runtime, 'pipewire-0')))
        if session:
            try:
                from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
                device = QMediaDevices.defaultAudioOutput()
                if device.isNull():
                    return
                fmt = QAudioFormat()
                fmt.setSampleRate(re_synth.SR)
                fmt.setChannelCount(1)
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
                self.sink = QAudioSink(device, fmt)
                self.buf = QBuffer()
                self.buf.setData(QByteArray(samples.tobytes()))
                self.buf.open(QIODevice.OpenModeFlag.ReadOnly)
                self.sink.start(self.buf)
                return
            except Exception:
                self.sink = None
                self.buf = None
        import shutil
        import subprocess
        player = shutil.which('paplay') or shutil.which('aplay')
        if not player:
            return
        cmd = [player]
        if os.path.basename(player) == 'aplay':
            cmd += ['-q', '-f', 'S16_LE', '-r', str(re_synth.SR), '-c', '1']
        try:
            self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            self._proc.stdin.write(samples.tobytes())
            self._proc.stdin.close()
        except OSError:
            self._proc = None

    def stop(self):
        if self.sink is not None:
            self.sink.stop()
            self.sink = None
        self.buf = None
        if self._proc is not None:
            self._proc.kill()
            self._proc = None


class PreviewTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.which = QComboBox()
        self.which.currentIndexChanged.connect(lambda _i: self.refresh())
        bar.addWidget(QLabel('地图'))
        bar.addWidget(self.which)
        play = QPushButton('运行 PC')
        play.clicked.connect(lambda: self.window.build_tab.run('pc'))
        bar.addWidget(play)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.view = QLabel()
        sc = QScrollArea()
        sc.setWidget(self.view)
        lay.addWidget(sc, 1)
        lay.addWidget(QLabel('这里按 NES 的 16×16 属性块上色，色 0 用共用背景色，和游戏画面一致。'))

    def load(self, project):
        self.which.blockSignals(True)
        self.which.clear()
        for m in project.maps:
            self.which.addItem(m.name, m.name)
        self.which.blockSignals(False)
        self.refresh()

    def refresh(self):
        project = self.window.project
        if not project:
            return
        name = self.which.currentData()
        game_map = project.map_by_name(name) if name else (project.maps[0] if project.maps else None)
        if not game_map:
            return
        scale = 2 if game_map.w <= 32 else 1
        img = map_image(project, game_map, scale, True, True, True)
        self.view.setPixmap(QPixmap_from(img))
        self.view.resize(img.size())


class CodeTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('游戏逻辑仍是 C 文件 game.c。这里只做简单高亮，保存后和别的资源一起写入磁盘。'))
        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.hi = CHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._changed)
        lay.addWidget(self.editor)
        self._lock = False

    def load(self, project):
        self._lock = True
        self.editor.setPlainText(project.code)
        self._lock = False

    def _changed(self):
        if self._lock or not self.window.project:
            return
        self.window.project.code = self.editor.toPlainText()
        self.window.project.dirty['code'] = True
        self.window.touch()

    def flush(self):
        if self.window.project:
            self.window.project.code = self.editor.toPlainText()


class BuildTab(QWidget):
    def __init__(self, window):
        QWidget.__init__(self)
        self.window = window
        self.proc = None
        self.pending_run = None
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        for target, label in (('pc', '编译 PC'), ('uefi', '编译 UEFI'), ('img', '编译 UEFI 镜像'),
                              ('nes', '编译 NES'), ('gba', '编译 GBA')):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, t=target: self.start(t))
            row.addWidget(b)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        for target, label in (('pc', '运行 PC'), ('nes', '运行 NES'), ('gba', '运行 GBA'), ('uefi', '运行 UEFI')):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, t=target: self.run(t))
            row2.addWidget(b)
        deps = QPushButton('检查依赖')
        deps.clicked.connect(self.show_deps)
        row2.addWidget(deps)
        lay.addLayout(row2)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        self.hint = QLabel(' ')
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

    def start(self, target):
        if not self.window.project:
            QMessageBox.information(self, '编译', '先打开一个游戏。')
            return
        if self.proc is not None:
            QMessageBox.information(self, '编译', '已经有一个编译在进行。')
            return
        self.window.save_all()
        self.log.appendPlainText('\n$ make GAME=%s %s\n' % (self.window.project.name, target))
        self.hint.setText('正在编译…')
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(self.window.repo)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._finished)
        self.proc.start('make', ['GAME=%s' % self.window.project.name, target])

    def _read(self):
        if self.proc:
            self.log.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode('utf-8', 'replace').rstrip())

    def _finished(self, code, _status):
        self._read()
        self.proc = None
        text = self.log.toPlainText()
        tips = re_build.hints_for(text)
        if code == 0:
            self.hint.setText('编译完成。')
            self.log.appendPlainText('—— 编译完成 ——')
        else:
            self.hint.setText('编译失败（退出码 %d）。\n%s' % (code, '\n'.join(tips)))
            self.log.appendPlainText('—— 编译失败，退出码 %d ——' % code)
            for tip in tips:
                self.log.appendPlainText(tip)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        self.window.build_finished(code)

    def run(self, target):
        if not self.window.project:
            return
        if target != 'pc' and self.proc is not None:
            return
        argv, err = re_build.launch_argv(self.window.repo, self.window.project.name, target)
        if err:
            # PC can be built first.
            if target == 'pc' and '先点' in err:
                self.pending_run = 'pc'
                self.start('pc')
                return
            QMessageBox.warning(self, '运行', err)
            return
        QProcess.startDetached(argv[0], argv[1:])

    def show_deps(self):
        rows, packages = re_build.dependency_rows()
        lines = []
        for row in rows:
            mark = '已安装' if row['ok'] else '缺少'
            lines.append('%s  %s  (%s)  %s' % (mark, row['desc'], row['command'], row['package']))
        text = '\n'.join(lines)
        if packages:
            text += '\n\n一次安装缺少的包：\nsudo apt install ' + packages
            text += '\n\n编辑器在 Ubuntu 26.04 上还可以：sudo apt install python3-pyside6 python3-pyside6.qtmultimedia'
        else:
            text += '\n\n需要的工具都在。'
        box = QMessageBox(self)
        box.setWindowTitle('依赖')
        box.setText(text)
        box.exec()


class NewDialog(QDialog):
    def __init__(self, games, parent):
        QDialog.__init__(self, parent)
        self.setWindowTitle('新建游戏')
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('目录名，放在 games/ 下面。小写字母开头。'))
        self.name = QLineEdit()
        lay.addWidget(self.name)
        lay.addWidget(QLabel('从哪个例子复制'))
        self.template = QComboBox()
        self.template.addItem('空白（带字体图块）', '')
        for fn in sorted(os.listdir(games)):
            path = os.path.join(games, fn)
            if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'game.c')):
                self.template.addItem(fn, path)
        lay.addWidget(self.template)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class MainWindow(QMainWindow):
    def __init__(self, repo):
        QMainWindow.__init__(self)
        self.repo = repo
        self.games = os.path.join(repo, 'games')
        self.project = None
        self.build_done = []
        self.setWindowTitle('RetroEngine 编辑器')
        icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')
        if os.path.isfile(icon):
            self.setWindowIcon(QIcon(icon))
        self.tile_tab = TileTab(self)
        self.palette_tab = PaletteTab(self)
        self.map_tab = MapTab(self)
        self.music_tab = MusicTab(self)
        self.preview_tab = PreviewTab(self)
        self.code_tab = CodeTab(self)
        self.build_tab = BuildTab(self)
        self.tabs = QTabWidget()
        for widget, title in (
            (self.tile_tab, '图块'), (self.palette_tab, '调色板'), (self.map_tab, '地图'),
            (self.music_tab, '音乐'), (self.preview_tab, '预览'), (self.code_tab, '代码'),
            (self.build_tab, '编译'),
        ):
            self.tabs.addTab(widget, title)
        self.tabs.currentChanged.connect(self._tab)
        self.setCentralWidget(self.tabs)
        self._menus()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage('打开 games 目录里的一个游戏，或新建一个。')

    def _menus(self):
        file_menu = self.menuBar().addMenu('文件')
        file_menu.addAction('新建游戏…', self.new_project)
        open_menu = file_menu.addMenu('打开')
        if os.path.isdir(self.games):
            for fn in sorted(os.listdir(self.games)):
                path = os.path.join(self.games, fn)
                if os.path.isdir(path) and os.path.isfile(os.path.join(path, 'game.c')):
                    open_menu.addAction(fn, lambda p=path: self.open_project(p))
        file_menu.addAction('打开文件夹…', self.open_folder)
        file_menu.addAction('保存', self.save_all)
        file_menu.addSeparator()
        file_menu.addAction('退出', self.close)
        edit = self.menuBar().addMenu('编辑')
        edit.addAction('撤销', self.undo)
        edit.addAction('重做', self.redo)

    def _tab(self, index):
        if self.tabs.widget(index) is self.preview_tab:
            self.preview_tab.refresh()
        if self.tabs.widget(index) is self.map_tab:
            self.map_tab.refresh()

    def touch(self):
        if not self.project:
            return
        mark = ' *' if self.project.any_dirty() else ''
        self.setWindowTitle('RetroEngine 编辑器 — %s%s' % (self.project.name, mark))
        self.statusBar().showMessage(self.project.root + mark)

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, '打开游戏', self.games)
        if path:
            self.open_project(path)

    def open_project(self, path):
        try:
            project = data.Project(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, '打开失败', str(exc))
            return
        self.project = project
        self.tile_tab.load(project)
        self.palette_tab.load(project)
        self.map_tab.load(project)
        self.music_tab.load(project)
        self.preview_tab.load(project)
        self.code_tab.load(project)
        self.touch()

    def new_project(self):
        dialog = NewDialog(self.games, self)
        if dialog.exec() != QDialog.Accepted:
            return
        name = dialog.name.text().strip()
        if not name or not name[0].isalpha() or not all(c.isalnum() or c == '_' for c in name):
            QMessageBox.warning(self, '新建', '名字用字母开头，后面可以是字母、数字或下划线。')
            return
        template = dialog.template.currentData() or None
        try:
            path = data.create_project(self.games, name, template)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, '新建失败', str(exc))
            return
        self.open_project(path)

    def save_all(self):
        if not self.project:
            return
        self.code_tab.flush()
        try:
            self.project.save()
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, '保存失败', str(exc))
            return
        self.touch()

    def undo(self):
        widget = self.tabs.currentWidget()
        if hasattr(widget, 'undo'):
            widget.undo()

    def redo(self):
        widget = self.tabs.currentWidget()
        if hasattr(widget, 'redo'):
            widget.redo()

    def build_finished(self, code):
        self.build_done.append(code)
        if code == 0 and self.build_tab.pending_run:
            target = self.build_tab.pending_run
            self.build_tab.pending_run = None
            self.build_tab.run(target)

    def closeEvent(self, event):
        if self.project and self.project.any_dirty():
            answer = QMessageBox.question(self, '保存', '有没保存的修改。现在保存吗？')
            if answer == QMessageBox.Yes:
                self.save_all()
        event.accept()


def apply_style(app):
    app.setFont(QFont(APP_FONT, 10))
    app.setStyleSheet('''
        QWidget { background:#1e1e1e; color:#e8e8e8; }
        QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QListWidget, QTableWidget {
            background:#2a2a2a; color:#eee; }
        QPushButton { background:#3a3a3a; border:1px solid #666; padding:4px 8px; }
        QHeaderView::section { background:#333; color:#ddd; }
        QScrollArea { background:#1e1e1e; }
        QMenuBar, QMenu { background:#2a2a2a; color:#eee; }
    ''')


def main():
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '0')
    app = QApplication(sys.argv)
    apply_style(app)
    win = MainWindow(REPO)
    if len(sys.argv) > 1:
        win.open_project(os.path.abspath(sys.argv[1]))
    else:
        default = os.path.join(REPO, 'games', 'breakout')
        if os.path.isdir(default):
            win.open_project(default)
    win.resize(1200, 780)
    win.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
