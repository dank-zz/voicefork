"""Desktop UI (PySide6).  python -m voicefork gui

Two tabs share one Start/Stop button:
  Effects   - the numpy effect presets (runs on any PC)
  AI Voice  - RVC voices (NVIDIA GPU); effect presets can be layered on top

Anything slow (loading torch/models, CUDA warm-up) runs in a worker thread so
the window never freezes.
"""
from __future__ import annotations

import math
import os
import sys
import traceback

from PySide6.QtCore import QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider, QTabWidget,
    QVBoxLayout, QWidget,
)

from .presets import PRESETS

# Graphite + white, with one red that only appears while you're live.
GROUND, SURFACE, RAISED, LINE = "#101113", "#17181b", "#24262b", "#2a2c31"
INK, MUTED, ON_AIR = "#ececef", "#8a8d96", "#ff5a4e"
MONO = "'Cascadia Mono', Consolas, 'DejaVu Sans Mono', monospace"
STYLE = f"""
QWidget {{ background: {GROUND}; color: {INK}; font-size: 13px; }}
QToolTip {{ background: {RAISED}; color: {INK}; border: 1px solid {LINE}; padding: 4px 6px; }}
QLabel#brand {{ font-size: 15px; font-weight: 600; }}
QLabel#section {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#muted, QFormLayout QLabel {{ color: {MUTED}; }}
QLabel#mono {{ color: {MUTED}; font-family: {MONO}; font-size: 12px; }}
QLabel#value {{ font-family: {MONO}; font-size: 12px; }}
QLabel#field {{ color: #b5b7be; }}
QLabel#meterlab {{ color: {MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 1px; }}
QFrame#hr {{ background: #222428; max-height: 1px; min-height: 1px; border: none; }}
QFrame#footer {{ border-top: 1px solid #222428; }}
QFrame#segbox {{ background: {SURFACE}; border: 1px solid #25272c; border-radius: 7px; }}
QPushButton#route {{ text-align: left; padding: 9px 12px; background: {SURFACE}; border-color: #25272c; border-radius: 8px; }}
QPushButton#setup {{ text-align: left; padding: 9px 12px; color: {ON_AIR}; background: #1c1312; border-color: #3a2321; border-radius: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a3c42; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QLabel#pill {{ font-size: 11px; font-weight: 600; letter-spacing: 1px; padding: 4px 10px;
              border-radius: 11px; border: 1px solid {LINE}; color: {MUTED}; }}
QLabel#pill[state="live"] {{ color: {ON_AIR}; border-color: #3a2321; background: #1c1312; }}
QLabel#pill[state="busy"] {{ color: {INK}; }}

QTabWidget::pane {{ border: none; top: 8px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: {SURFACE}; color: {MUTED}; padding: 6px 16px; margin: 0;
               border: 1px solid {LINE}; font-weight: 500; }}
QTabBar::tab:first {{ border-top-left-radius: 7px; border-bottom-left-radius: 7px; border-right: none; }}
QTabBar::tab:last {{ border-top-right-radius: 7px; border-bottom-right-radius: 7px; border-left: none; }}
QTabBar::tab:selected {{ background: {LINE}; color: #ffffff; }}

QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 6px; padding: 7px 12px; }}
QPushButton:hover {{ border-color: #4a4d55; }}
QPushButton:checked {{ background: {RAISED}; border-color: {INK}; color: #ffffff; }}
QPushButton:disabled {{ color: #5b5e66; }}
QPushButton#tile {{ text-align: left; padding: 10px 12px; background: {SURFACE}; border-color: #25272c; }}
QPushButton#tile:checked {{ background: {RAISED}; border-color: {INK}; }}
QPushButton#seg {{ border: none; border-radius: 5px; padding: 4px 12px; background: transparent; color: {MUTED}; }}
QPushButton#seg:checked {{ background: {LINE}; color: #ffffff; }}
QPushButton#start {{ background: {INK}; color: {GROUND}; border: none; border-radius: 8px;
                    padding: 10px 22px; font-weight: 600; }}
QPushButton#start:disabled {{ background: {RAISED}; color: {MUTED}; }}
QPushButton#start[live="true"] {{ background: transparent; color: {ON_AIR}; border: 1px solid {ON_AIR}; }}

QComboBox, QListWidget {{ background: {SURFACE}; border: 1px solid #25272c; border-radius: 6px; padding: 5px 8px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; selection-background-color: {RAISED}; }}
QListWidget {{ padding: 4px; outline: none; }}
QListWidget::item {{ padding: 4px 8px; border-radius: 5px; color: #c9cbd1; }}
QListWidget::item:selected {{ background: {RAISED}; color: #ffffff; }}
QListWidget::item:hover {{ background: #1d1f23; }}

QCheckBox {{ spacing: 8px; color: #b5b7be; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #4a4d55; border-radius: 3px; background: {SURFACE}; }}
QCheckBox::indicator:checked {{ background: {INK}; border-color: {INK}; }}

QProgressBar {{ background: {RAISED}; border: none; height: 6px; max-height: 6px; }}
QProgressBar::chunk {{ background: {INK}; width: 9px; margin-right: 2px; }}
QSlider::groove:horizontal {{ height: 2px; background: #2e3036; }}
QSlider::sub-page:horizontal {{ height: 2px; background: {INK}; }}
QSlider::handle:horizontal {{ background: #ffffff; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a3c42; }}
QSlider::handle:horizontal:disabled {{ background: #5b5e66; }}
"""

def short_device(name: str) -> str:
    """'Mikrofon (Yeti X)' -> 'Yeti X'."""
    if "(" in name and name.rstrip().endswith(")"):
        inner = name[name.index("(") + 1:name.rindex(")")].strip()
        return inner or name
    return name


class Switch(QCheckBox):
    """A checkbox painted as a toggle switch. Drawn by hand: Qt stylesheets can't draw the knob,
    and image-based indicators don't load reliably on every setup."""

    TRACK_W, TRACK_H, GAP = 28, 16, 8

    def __init__(self, text, checked):
        super().__init__(text)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(self.TRACK_W + self.GAP + fm.horizontalAdvance(self.text()) + 2,
                     max(self.TRACK_H, fm.height()) + 4)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on, enabled = self.isChecked(), self.isEnabled()
        y = (self.height() - self.TRACK_H) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(INK if on and enabled else ("#5b5e66" if on else "#2e3036")))
        p.drawRoundedRect(QRectF(0, y, self.TRACK_W, self.TRACK_H), 8, 8)
        p.setBrush(QColor(GROUND if on else MUTED))
        cx = self.TRACK_W - 8 if on else 8
        p.drawEllipse(QPointF(cx, y + 8), 6, 6)
        if self.hasFocus():
            p.setPen(QPen(QColor(ON_AIR), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(-1, y - 1, self.TRACK_W + 2, self.TRACK_H + 2), 9, 9)
        p.setPen(QColor("#b5b7be" if enabled else "#5b5e66"))
        p.setFont(self.font())
        p.drawText(QRectF(self.TRACK_W + self.GAP, 0, self.width(), self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


# The mark from the mockup: five bars of a waveform, drawn on a 24-unit grid.
LOGO_BARS = ((4, 10, 14), (8, 7, 17), (12, 4, 20), (16, 8, 16), (20, 11, 13))


def paint_logo(p: QPainter, size: float, color: str = INK, width: float = 1.8):
    k = size / 24
    pen = QPen(QColor(color), width * k)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for x, y0, y1 in LOGO_BARS:
        p.drawLine(QPointF(x * k, y0 * k), QPointF(x * k, y1 * k))


class Logo(QWidget):
    def __init__(self, size=20):
        super().__init__()
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_logo(p, self.width())
        p.end()


def app_icon() -> QIcon:
    """Window/taskbar icon: the mark in white on a dark rounded square."""
    icon = QIcon()
    for n in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(n, n)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(GROUND))
        p.drawRoundedRect(QRectF(0, 0, n, n), n * 0.22, n * 0.22)
        p.translate(n * 0.14, n * 0.14)
        paint_logo(p, n * 0.72, width=2.2)
        p.end()
        icon.addPixmap(pm)
    return icon


def switch(text, checked):
    return Switch(text, checked)


def field(text):
    lab = QLabel(text)
    lab.setObjectName("field")
    return lab


from .ai.hwcheck import MODES as QUALITY  # noqa: E402  name -> (block s, pitch tracker, context s)

HW_CHECK_VERSION = "1"   # bump to make everyone re-run the speed check


class Task(QThread):
    """Run fn() off the UI thread, report back with a signal."""
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:  # noqa: BLE001 - shown to the user
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


TILE_DESC = {  # short enough for three tiles across a 560 px window
    "clean": "your normal voice", "deep": "lower, bigger", "chipmunk": "fast and squeaky",
    "demon": "low and gritty", "giant": "huge, in a hall", "robot": "metallic",
    "alien": "warbly sci-fi", "radio": "walkie-talkie", "megaphone": "loud and honky",
    "cave": "echoing", "8bit": "retro console",
}


def section(text):
    lab = QLabel(text.upper())
    lab.setObjectName("section")
    return lab


class Segmented(QWidget):
    """A row of joined toggle buttons; API mirrors the bits of QComboBox we use."""

    def __init__(self, options, current):
        super().__init__()
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QFrame()
        box.setObjectName("segbox")
        outer.addWidget(box)
        outer.addStretch(1)
        row = QHBoxLayout(box)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        for opt in options:
            b = QPushButton(opt)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setChecked(opt == current)
            self.group.addButton(b)
            row.addWidget(b)
        if self.group.checkedButton() is None:
            self.group.buttons()[0].setChecked(True)

    def currentText(self):
        return self.group.checkedButton().text()

    def setCurrentText(self, text):
        for b in self.group.buttons():
            if b.text() == text:
                b.setChecked(True)


def labeled_slider(lo, hi, value, scale, fmt):
    """Integer QSlider showing value/scale with a live label."""
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(value)
    lab = QLabel(fmt(value / scale))
    lab.setObjectName("value")
    lab.setMinimumWidth(56)
    lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    s.valueChanged.connect(lambda v: lab.setText(fmt(v / scale)))
    row = QHBoxLayout()
    row.addWidget(s, 1)
    row.addWidget(lab)
    return s, row


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voicefork")
        self.setMinimumSize(560, 700)
        self.cfg = QSettings("voicefork", "voicefork")
        if not self.cfg.allKeys():               # carry settings over from the app's old name
            old = QSettings("voicechanger", "voicechanger")
            for k in old.allKeys():
                self.cfg.setValue(k, old.value(k))
        self.engine = None          # VoiceEngine or AIVoiceEngine
        self.mode = None            # "fx" or "ai"
        self.task: Task | None = None
        self.shared = None          # AI: HuBERT/RMVPE, kept between starts
        self.voice_cache = {}       # AI: name -> RVCVoice
        self.voice_settings = None  # AI: shared VoiceSettings
        self.mon = None             # Monitor (hear yourself)
        self._orphans: list = []     # tasks left running after the user skipped them
        self.cable_skip = False     # user chose "Go live anyway" without a virtual cable

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(root)

        head = QHBoxLayout()
        head.setContentsMargins(20, 14, 20, 14)
        head.setSpacing(10)
        head.addWidget(Logo(20))
        brand = QLabel("Voicefork")
        brand.setObjectName("brand")
        head.addWidget(brand)
        head.addStretch(1)
        typ = QPushButton("Type")
        typ.setToolTip("Type to speak in your current voice (give it a hotkey under Hotkeys)")
        typ.clicked.connect(self._open_type)
        head.addWidget(typ)
        keys = QPushButton("Hotkeys")
        keys.clicked.connect(self._open_hotkeys)
        head.addWidget(keys)
        self.pill = QLabel("OFF")
        self.pill.setObjectName("pill")
        head.addWidget(self.pill)
        outer.addLayout(head)
        hr = QFrame()
        hr.setObjectName("hr")
        outer.addWidget(hr)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(14)
        outer.addWidget(body, 1)

        # routing: one summary row; the device pickers fold out under it
        self.route = QPushButton()
        self.route.setObjectName("route")
        self.route.clicked.connect(self._toggle_devices)
        lay.addWidget(self.route)
        self.setup_btn = QPushButton("No virtual mic yet: set it up so Discord can hear you  →")
        self.setup_btn.setObjectName("setup")
        self.setup_btn.clicked.connect(lambda: self._open_cable_setup())
        self.setup_btn.hide()
        lay.addWidget(self.setup_btn)
        self.dev_panel = QWidget()
        form = QFormLayout(self.dev_panel)
        form.setContentsMargins(0, 0, 0, 0)
        self.mic = QComboBox()
        self.out = QComboBox()
        self.phones = QComboBox()
        form.addRow(field("Microphone"), self.mic)
        form.addRow(field("Output"), self.out)
        form.addRow(field("Monitor in"), self.phones)
        self.gate, gate_row = labeled_slider(-80, -20, int(self.cfg.value("gate", -50)), 1,
                                             lambda v: f"{v:.0f} dB")
        self.gate.setToolTip("Lower = lets quieter sounds through. Raise if keyboard/room noise leaks.")
        form.addRow(field("Gate level"), gate_row)
        self.dev_panel.hide()
        lay.addWidget(self.dev_panel)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._fx_tab(), "Effects")
        self.tabs.addTab(self._ai_tab(), "AI voice")
        from .soundboard import ClipCache
        from .soundboard_ui import SoundboardTab
        self.sb_mix = None          # Mixer inside the live engine (others hear it)
        self.sb_local = None        # LocalPlayer on your headphones (you hear it)
        self.clip_cache = ClipCache()
        self.sb_tab = SoundboardTab(self.cfg, lambda: self.mic.currentData())
        self.sb_tab.play.connect(self._play_clip)
        self.sb_tab.stop_all.connect(self._stop_clips)
        self.sb_tab.volume.connect(self._sb_volume)
        self.sb_tab.changed.connect(lambda: self._load_hotkeys())
        self.tabs.addTab(self.sb_tab, "Soundboard")
        self.audio_tab = int(self.cfg.value("audio_tab", 0))   # which mode Go live starts: 0 effects, 1 AI
        self.tabs.currentChanged.connect(self._tab_changed)
        lay.addWidget(self.tabs, 1)

        # footer band: meters, switches, mute + go live, stats
        foot = QFrame()
        foot.setObjectName("footer")
        f = QVBoxLayout(foot)
        f.setContentsMargins(20, 14, 20, 14)
        f.setSpacing(10)
        meters = QGridLayout()
        meters.setHorizontalSpacing(10)
        meters.setVerticalSpacing(6)
        self.meter_in, self.meter = QProgressBar(), QProgressBar()
        for r, (name, bar) in enumerate((("IN", self.meter_in), ("OUT", self.meter))):
            lab = QLabel(name)
            lab.setObjectName("meterlab")
            lab.setFixedWidth(28)
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            meters.addWidget(lab, r, 0)
            meters.addWidget(bar, r, 1)
        f.addLayout(meters)

        row = QHBoxLayout()
        row.setSpacing(14)
        self.gate_on = switch("Gate", self.cfg.value("gate_on", "true") == "true")
        self.gate_on.setToolTip("Silences the mic between words. Turn off if it cuts your voice.")
        row.addWidget(self.gate_on)
        self.gate_val = QLabel(f"{int(self.cfg.value('gate', -50))} dB")
        self.gate_val.setObjectName("mono")
        self.gate_val.setToolTip("Gate level: change it under the routing row (click it)")
        row.addWidget(self.gate_val)
        self.gate.setEnabled(self.gate_on.isChecked())
        self.gate.valueChanged.connect(lambda v: self.gate_val.setText(f"{v} dB"))
        self.mon_on = switch("Monitor", self.cfg.value("monitor", "false") == "true")
        self.mon_on.setToolTip("Hear your changed voice live (pick the device under Change)")
        row.addWidget(self.mon_on)
        self.bypass = switch("Real voice", False)
        self.bypass.setToolTip("AI voice: let your real voice through for a moment")
        self.bypass.toggled.connect(lambda on: setattr(self.engine, "bypass", on)
                                    if self.mode == "ai" and self.engine else None)
        row.addWidget(self.bypass)
        row.addStretch(1)
        self.mute = QPushButton("Mute")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self._mute)
        row.addWidget(self.mute)
        self.start = QPushButton("Go live")
        self.start.setObjectName("start")
        self.start.clicked.connect(self._start_stop)
        row.addWidget(self.start)
        f.addLayout(row)

        stats = QHBoxLayout()
        self.status = QLabel("off")
        self.status.setObjectName("mono")
        self.hw = QLabel("")
        self.hw.setObjectName("mono")
        stats.addWidget(self.status, 1)
        stats.addWidget(self.hw)
        f.addLayout(stats)
        outer.addWidget(foot)

        self._fill_devices()
        self.mon_on.toggled.connect(lambda _: (self._attach_monitor(), self._update_route()))
        self.phones.currentIndexChanged.connect(lambda _: (self._attach_monitor(), self._update_route()))
        self.mic.currentIndexChanged.connect(lambda _: self._update_route())
        self.out.currentIndexChanged.connect(lambda _: self._update_route())
        self._update_route()
        self.gate_on.toggled.connect(self._gate_changed)
        self.gate.valueChanged.connect(self._gate_changed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self.tabs.setCurrentIndex(int(self.cfg.value("tab", 0)))

        from .hotkeys import HotkeyManager
        self.ptt_held = False
        self.hk = HotkeyManager(self)
        self.hk.action.connect(self._hotkey_action)
        self.hk.ptt.connect(self._on_ptt)
        from .type_popup import TypePopup
        self.type_popup = TypePopup()
        self.type_popup.setStyleSheet(STYLE)
        self.type_popup.speak.connect(self._speak)
        self.tts_tasks: list = []
        self._load_hotkeys()
        if not self.hk.start():
            self.status.setText(self.hk.error)

    # ---------------------------------------------------------------- tabs
    def _preset_grid(self, on_pick, include_clean_label=None):
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)
        group = QButtonGroup(box)
        group.setExclusive(True)
        self.fx_buttons = {}
        for i, (name, (desc, _)) in enumerate(PRESETS.items()):
            label = include_clean_label if (name == "clean" and include_clean_label) else name.capitalize()
            b = QPushButton(f"{label}\n{TILE_DESC.get(name, desc.lower())}")
            b.setObjectName("tile")
            b.setCheckable(True)
            b.setMinimumHeight(58)
            b.clicked.connect(lambda _=False, n=name: on_pick(n))
            group.addButton(b)
            self.fx_buttons[name] = b
            grid.addWidget(b, i // 3, i % 3)
            if name == "clean":
                b.setChecked(True)
        return box, group

    def _fx_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(section("Presets"))
        grid, self.fx_group = self._preset_grid(self._pick_fx)
        v.addWidget(grid)
        v.addStretch(1)
        self.fx_preset = "clean"
        return w

    def _ai_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(section("Voices"))
        top.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._fill_voices)
        folder = QPushButton("Folder")
        folder.setToolTip("Open the voices folder")
        folder.clicked.connect(self._open_voices)
        mixer = QPushButton("Blend")
        mixer.setToolTip("Mix two voices into a new one")
        mixer.clicked.connect(self._open_blend)
        store = QPushButton("Get voices")
        store.clicked.connect(self._open_store)
        make = QPushButton("Make my voice")
        make.setToolTip("Record yourself and train your own AI voice")
        make.clicked.connect(self._open_train)
        top.addWidget(store)
        top.addWidget(mixer)
        top.addWidget(make)
        top.addWidget(refresh)
        top.addWidget(folder)
        v.addLayout(top)

        self.voice_list = QListWidget()
        self.voice_list.setMinimumHeight(150)
        self.voice_list.currentTextChanged.connect(self._pick_voice)
        v.addWidget(self.voice_list, 1)

        form = QFormLayout()
        self.pitch, r = labeled_slider(-24, 24, int(self.cfg.value("pitch", 0)), 1, lambda x: f"{x:+.0f} st")
        self.pitch.setToolTip("+12 if you're male and the voice is female, -12 the other way")
        self.pitch.valueChanged.connect(self._voice_params)
        form.addRow(field("Pitch"), r)
        self.formant, r = labeled_slider(-10, 10, int(self.cfg.value("formant", 0)), 2, lambda x: f"{x:+.1f}")
        self.formant.setToolTip("Voice 'size'. Small values (±1) sound most natural.")
        self.formant.valueChanged.connect(self._voice_params)
        form.addRow(field("Formant"), r)
        self.index, r = labeled_slider(0, 100, int(self.cfg.value("index", 0)), 100, lambda x: f"{x:.2f}")
        self.index.setToolTip("Pull timbre closer to the target (needs .index). Too high slurs words.")
        self.index.valueChanged.connect(self._voice_params)
        form.addRow(field("Similarity"), r)
        self.quality = Segmented(list(QUALITY), self.cfg.value("quality", "Balanced"))
        self.quality.setToolTip("Fast = least delay. Crisp = clearest words, more delay. Applies on Start.")
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.quality, 1)
        speed = QPushButton("Test speed")
        speed.setToolTip("Measure this PC and pick the best Mode (runs automatically the first time)")
        speed.clicked.connect(lambda: self._run_hw_check(then_start=False))
        mode_row.addWidget(speed)
        form.addRow(field("Mode"), mode_row)
        self.post = QComboBox()
        self.post.setMaximumWidth(200)
        self.post.addItem("None", None)
        for name in PRESETS:
            if name != "clean":
                self.post.addItem(name.capitalize(), name)
        self.post.currentIndexChanged.connect(self._pick_post)
        form.addRow(field("Add effect"), self.post)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        v.addLayout(form)
        self._fill_voices()
        return w

    # ---------------------------------------------------------------- devices
    def _fill_devices(self):
        try:
            import sounddevice as sd

            from .devices import find_device, has_virtual_cable, is_virtual, preferred_hostapi
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"Audio unavailable: {e}")
            return
        for combo in (self.mic, self.out, self.phones):
            combo.blockSignals(True)
        pref = preferred_hostapi()
        devs = sd.query_devices()
        for combo, key, kind in ((self.mic, "max_input_channels", "input"),
                                 (self.out, "max_output_channels", "output")):
            combo.clear()
            for i, d in enumerate(devs):
                if d[key] > 0 and (pref is None or d["hostapi"] == pref):
                    combo.addItem(d["name"], i)
            saved = self.cfg.value(kind)
            pos = combo.findText(saved) if saved else -1
            if pos < 0:
                try:
                    pos = combo.findData(find_device(None, kind))
                except SystemExit:
                    pos = -1
            if pos >= 0:
                combo.setCurrentIndex(pos)
        # headphones: real outputs only (not the virtual cable)
        self.phones.clear()
        for i, d in enumerate(devs):
            if d["max_output_channels"] > 0 and (pref is None or d["hostapi"] == pref) \
                    and "cable" not in d["name"].lower() and not is_virtual(d["name"]):
                self.phones.addItem(d["name"], i)
        saved = self.cfg.value("phones")
        pos = self.phones.findText(saved) if saved else -1
        if pos < 0 and pref is not None:
            pos = self.phones.findData(sd.query_hostapis(pref)["default_output_device"])
        if pos >= 0:
            self.phones.setCurrentIndex(pos)
        for combo in (self.mic, self.out, self.phones):
            combo.blockSignals(False)
        self.setup_btn.setVisible(not has_virtual_cable(devs))

    def _output_is_virtual(self) -> bool:
        from .devices import is_virtual
        return is_virtual(self.out.currentText())

    def _open_cable_setup(self, going_live: bool = False) -> bool:
        """Returns True if the user chose to go live without a cable."""
        from .cable_setup import CableSetup

        def found():
            self._fill_devices()
            self._update_route()
        dlg = CableSetup(going_live, self)
        dlg.found.connect(found)
        return bool(dlg.exec())

    def _update_route(self):
        mic = short_device(self.mic.currentText()) or "no mic"
        out = short_device(self.out.currentText()) or "no output"
        mon = f"monitor: {short_device(self.phones.currentText())}" if self.mon_on.isChecked() else "monitor off"
        arrow = "\u2192"
        self.route.setText(f"{mic}  {arrow}  {out}   \u00b7  {mon}")
        self.route.setToolTip("Change microphone, output and monitor devices")

    def _toggle_devices(self):
        self.dev_panel.setVisible(not self.dev_panel.isVisible())

    def _fill_voices(self):
        from .ai import assets
        current = self.cfg.value("voice", "")
        self.voice_list.blockSignals(True)
        self.voice_list.clear()
        names = assets.list_voices()
        self.voice_list.addItems(names)
        if current in names:
            self.voice_list.setCurrentRow(names.index(current))
        elif names:
            self.voice_list.setCurrentRow(0)
        self.voice_list.blockSignals(False)
        if not names:
            self.voice_list.addItem("No voices yet. Click Get voices.")
            self.voice_list.item(0).setFlags(Qt.NoItemFlags)

    def _open_store(self):
        from .voice_store import VoiceStore
        if getattr(self, "store", None) is None:
            self.store = VoiceStore(self)
            self.store.changed.connect(self._fill_voices)
        self.store.show()
        self.store.raise_()

    def _open_train(self):
        from .train_dialog import TrainDialog
        if getattr(self, "train_dlg", None) is None:
            self.train_dlg = TrainDialog(lambda: self.mic.currentData(), lambda: self.engine is not None, self)
            self.train_dlg.trained.connect(lambda _: (self._fill_voices(), self._load_hotkeys()))
        self.train_dlg.show()
        self.train_dlg.raise_()

    def _open_blend(self):
        from .ai import assets, preview
        from .blend_dialog import BlendDialog
        voices = assets.list_voices()
        if len(voices) < 2:
            return self._error("Blending needs at least two voices. Get some under Get voices.")

        def play(y, sr):
            try:
                preview.play(y, sr, self.phones.currentData())
            except Exception as e:  # noqa: BLE001
                self._error(f"Could not play audio: {e}")

        dlg = BlendDialog(voices, self.pitch.value(), play, self)
        dlg.saved.connect(lambda _: (self._fill_voices(), self._load_hotkeys()))
        dlg.exec()

    def _open_voices(self):
        from .ai import assets
        d = assets.voices_dir()
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    # ---------------------------------------------------------------- start/stop
    @staticmethod
    def _restyle(w, prop, value):
        w.setProperty(prop, value)
        w.style().unpolish(w)
        w.style().polish(w)

    def _busy(self, text):
        self.start.setEnabled(False)
        self.status.setText(text)
        self.pill.setText("LOADING")
        self._restyle(self.pill, "state", "busy")

    def _set_live(self, live: bool):
        self.start.setEnabled(True)
        self.start.setText("Stop" if live else "Go live")
        self._restyle(self.start, "live", "true" if live else "false")
        self.pill.setText("ON AIR" if live else "OFF")
        self._restyle(self.pill, "state", "live" if live else "off")

    def _task_running(self):
        return self.task is not None and self.task.isRunning()

    def _start_stop(self):
        if self._task_running():
            return
        if self.engine:
            return self._stop()
        if not self._output_is_virtual() and not self.cable_skip:
            if not self._open_cable_setup(going_live=True):
                return
            self.cable_skip = not self._output_is_virtual()   # "Go live anyway": don't ask again
        if self.audio_tab == 0:
            self._start_fx()
        else:
            self._start_ai()

    def _stop(self):
        self._detach_monitor()
        self._detach_sb()
        if self.engine:
            self.engine.stop()
        self.engine, self.mode = None, None
        self._set_live(False)
        self.status.setText("off")
        self.meter.setValue(0)
        self.meter_in.setValue(0)
        self.hw.setText("")

    def _devices(self):
        return self.mic.currentData(), self.out.currentData()

    def _start_fx(self):
        from .engine import VoiceEngine
        inp, out = self._devices()
        if inp is None or out is None:
            return self._error("Pick a microphone and an output under the routing row.")
        try:
            eng = VoiceEngine(inp, out, preset=self.fx_preset, gate_db=self._gate_db())
            eng.start()
        except Exception as e:  # noqa: BLE001
            return self._error(f"Could not open audio devices:\n{e}")
        self._apply_mute(eng)
        self.engine, self.mode = eng, "fx"
        self.hw.setText("cpu effects")
        self._set_live(True)
        self._attach_monitor()
        self._attach_sb()

    def _run_hw_check(self, then_start: bool):
        """Measure this PC once and pick the Mode (and warn if AI voices can't run smoothly)."""
        if self._task_running() or self.engine:
            return self._error("Stop first, then test the speed.") if self.engine else None
        item = self.voice_list.currentItem()
        if not item or not (item.flags() & Qt.ItemIsSelectable):
            return self._error("Get a voice first (Get voices), then the speed test can run with it.")
        name = item.text()
        state = {"step": "starting", "skipped": False}

        def work():
            import sys
            from .ai import hwcheck
            task = self.task

            def progress(s):
                print(f"[speed test] {s}", file=sys.stderr, flush=True)   # ends up in crash-log.txt
                task.progress.emit(s)
            return hwcheck.check(name, progress)

        def on_progress(s):
            state["step"] = s
            self.status.setText(f"speed test: {s}")

        def watchdog():
            task = self.task
            if state["skipped"] or task is None or not task.isRunning():
                return
            ans = QMessageBox.question(
                self, "Voicefork",
                f"The speed test is taking long. It's stuck at:\n\n{state['step']}\n\n"
                "Skip it and use the standard mode? (You can run it again later with Test speed.)",
                QMessageBox.Yes | QMessageBox.No)
            if ans != QMessageBox.Yes:
                QTimer.singleShot(60_000, watchdog)
                return
            if not task.isRunning():   # finished while the question was open
                return
            state["skipped"] = True
            self._orphans.append(task)   # let it finish in the background; don't block Go live
            self.task = None
            try:
                import torch
                gpu = torch.cuda.is_available()
            except Exception:  # noqa: BLE001
                gpu = False
            self.cfg.setValue("hw/version", HW_CHECK_VERSION)
            self.quality.setCurrentText("Balanced" if gpu else "Laptop")
            self.status.setText(f"speed test skipped (stuck at: {state['step']})")
            self._set_live(False)

        def done(r):
            if state["skipped"]:
                return
            try:
                apply(r)
            except Exception as e:  # noqa: BLE001 - a broken result must not leave the UI on LOADING
                self._set_live(False)
                self._error(f"Speed test finished but the result couldn't be used: {e}")

        def apply(r):
            c = self.cfg
            c.setValue("hw/version", HW_CHECK_VERSION)
            c.setValue("hw/device", r.device)
            c.setValue("hw/name", r.device_name)
            self.quality.setCurrentText(r.mode)
            where = "GPU" if r.device == "cuda" else "processor (no NVIDIA GPU found)"
            loads = "   ".join(f"{m.lower()} {v * 100:.0f}%" for m, v in r.measured.items())
            self.status.setText(f"speed test: {loads}")
            self._set_live(False)
            if not r.ok:
                QMessageBox.warning(
                    self, "Voicefork",
                    f"This PC is too slow for AI voices in real time on its {where}: even {r.mode} mode "
                    f"needs {r.load * 100:.0f}% of the time it has, so the voice would crackle.\n\n"
                    "Effects work fine on any PC. You can still try AI voices, with more delay.")
            elif r.device != "cuda":
                QMessageBox.information(
                    self, "Voicefork",
                    f"No NVIDIA GPU found, so AI voices run on the processor in {r.mode} mode. "
                    "Expect roughly half a second of delay.")
            if then_start and r.ok:
                self._start_ai()

        self._busy("Testing this PC's speed once (about 20 seconds) …")
        self._run(work, done, on_progress)
        QTimer.singleShot(60_000, watchdog)

    def _start_ai(self):
        item = self.voice_list.currentItem()
        if not item or not (item.flags() & Qt.ItemIsSelectable):
            return self._error("Add a voice first: put a .pth (and .index) in a folder inside the voices folder.")
        if self.cfg.value("hw/version", "") != HW_CHECK_VERSION:
            return self._run_hw_check(then_start=True)
        inp, out = self._devices()
        if inp is None or out is None:
            return self._error("Pick a microphone and an output under the routing row.")
        name = item.text()
        block, f0, context = QUALITY[self.quality.currentText()]
        gate_db = self._gate_db()
        post = self.post.currentData()
        params = self._params()

        def work():
            from .ai import assets
            if assets.missing():
                assets.download()  # first run: fetch HuBERT + RMVPE
            from .ai.engine import AIVoiceEngine, StreamSettings
            voice = self._load_voice(name, f0, params)
            st = StreamSettings(block_time=block, context_time=context, gate_db=gate_db, post_preset=post)
            eng = AIVoiceEngine(voice, inp, out, st)
            eng.start()  # includes CUDA warm-up
            return eng

        self._busy(f"Loading {name} (first time takes a while) ...")
        self._run(work, self._ai_started)

    def _ai_started(self, eng):
        self.engine, self.mode = eng, "ai"
        try:
            import torch
            dev = self.shared.device
            self.hw.setText(f"{torch.cuda.get_device_name(dev).replace('NVIDIA GeForce ', '')} \u00b7 fp16"
                            if dev.type == "cuda" else "cpu")
        except Exception:  # noqa: BLE001
            self.hw.setText("")
        eng.bypass = self.bypass.isChecked()
        self._apply_mute(eng)
        self._set_live(True)
        self._attach_monitor()
        self._attach_sb()

    def _params(self):
        """Slider values, read on the UI thread (Qt widgets aren't thread-safe)."""
        return self.pitch.value(), self.formant.value() / 2, self.index.value() / 100

    def _load_voice(self, name, f0, params):
        """Runs in a worker thread."""
        import torch

        from .ai import assets
        from .ai.rvc import RVCVoice, SharedModels, VoiceSettings
        if self.shared is None:
            dev = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
            if dev.type == "cuda":
                torch.backends.cudnn.benchmark = True
            else:  # laptop mode: one thread per physical core is fastest for these models
                torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
            self.shared = SharedModels(dev, dev.type == "cuda")
            self.voice_settings = VoiceSettings()
        vs = self.voice_settings
        vs.f0_method = f0
        vs.pitch, vs.formant, vs.index_rate = params
        self.shared.load_rmvpe() if f0 == "rmvpe" else self.shared.load_fcpe()
        if name not in self.voice_cache:
            pth, idx = assets.find_voice(name)
            self.voice_cache[name] = RVCVoice(pth, self.shared, vs, idx)
        return self.voice_cache[name]

    def _run(self, fn, on_done, on_progress=None):
        self.task = Task(fn, self)
        if on_progress:
            self.task.progress.connect(on_progress)
        self.task.done.connect(on_done)
        self.task.failed.connect(self._task_failed)
        self.task.start()

    def _task_failed(self, msg):
        self._set_live(bool(self.engine))
        import sys
        outside_venv = sys.prefix == getattr(sys, "base_prefix", sys.prefix)
        if "WinError 193" in msg or ("torch" in msg and outside_venv):
            msg = ("Voicefork was started with your computer's main Python, which has a broken PyTorch.\n\n"
                   "Close this and start it with \"Start Voicefork.bat\" instead "
                   "(it uses its own clean copy).\n\nDetails: " + msg)
        elif "No module named" in msg:
            msg += "\n\nAI voices need the extra packages: run \"Start Voicefork.bat\" once to install them."
        self._error(msg)

    def _error(self, msg):
        self.status.setText("Error")
        QMessageBox.warning(self, "Voicefork", msg)

    # ---------------------------------------------------------------- live changes
    def _tab_changed(self, i):
        if i == 2 or i == self.audio_tab:   # the soundboard tab doesn't change the voice mode
            return
        self.audio_tab = i
        if self.engine:  # switching mode while live: restart in the new mode
            self._stop()
            self._start_stop()

    def _pick_fx(self, name):
        self.fx_preset = name
        if self.mode == "fx" and self.engine:
            self.engine.set_preset(name)

    def _pick_voice(self, name):
        if not name or self.mode != "ai" or not self.engine or self._task_running():
            return
        eng = self.engine
        f0 = QUALITY[self.quality.currentText()][1]
        params = self._params()

        def work():
            eng.switch_voice(self._load_voice(name, f0, params))
            return eng

        self._busy(f"Switching to {name} ...")
        self._run(work, self._ai_started)

    def _voice_params(self):
        vs = self.voice_settings
        if vs is not None:  # plain attribute writes; picked up on the next audio block
            vs.pitch, vs.formant, vs.index_rate = self._params()

    def _pick_post(self):
        if self.mode == "ai" and self.engine:
            self.engine.set_post(self.post.currentData())

    def _gate_db(self) -> float:
        return float(self.gate.value()) if self.gate_on.isChecked() else -120.0

    def _gate_changed(self, *_):
        self.gate.setEnabled(self.gate_on.isChecked())
        if self.engine and self.start.isEnabled():
            self.engine.set_gate(self._gate_db())

    def _detach_monitor(self):
        if self.engine is not None:
            self.engine.monitor = None
        if self.mon is not None:
            self.mon.stop()
            self.mon = None

    def _attach_monitor(self):
        self._detach_monitor()
        dev = self.phones.currentData()
        if not (self.engine and self.mon_on.isChecked() and dev is not None):
            return
        from .monitor import Monitor
        eng = self.engine
        block = getattr(eng, "block_frame", None) or eng.blocksize
        try:
            self.mon = Monitor(dev, eng.sr, block).start()
            eng.monitor = self.mon
        except Exception as e:  # noqa: BLE001
            self.mon = None
            self._error(f"Could not open headphones device:\n{e}")

    def _mute(self, on):
        self._apply_mute()
        self.mute.setText("Muted" if on else "Mute")

    # ---------------------------------------------------------------- soundboard
    def _attach_sb(self):
        from .soundboard import Mixer
        self._detach_sb()
        if self.engine is not None:
            self.sb_mix = Mixer(self.engine.sr)
            self.sb_mix.volume = self.sb_tab.vol.value() / 100
            self.engine.soundboard = self.sb_mix

    def _detach_sb(self):
        if self.engine is not None:
            self.engine.soundboard = None
        self.sb_mix = None

    def _play_clip(self, name: str):
        from .soundboard import list_clips
        clip = next((c for c in list_clips() if c.name == name), None)
        if clip is not None:
            self._play_samples(name, lambda sr: self.clip_cache.get(clip, sr), toggle=True)

    def _play_samples(self, name: str, samples_at, toggle: bool):
        """Send a sound to the virtual mic (when live) and to your headphones. samples_at(sr) -> array."""
        from .soundboard import LocalPlayer
        try:
            targets = []
            if self.sb_mix is not None:                                   # live: others hear it
                targets.append(self.sb_mix)
            if not (self.engine is not None and self.mon is not None):   # monitor isn't already playing it to you
                if self.sb_local is None:
                    self.sb_local = LocalPlayer(self.phones.currentData())
                    self.sb_local.mixer.volume = self.sb_tab.vol.value() / 100
                targets.append(self.sb_local.mixer)
            for m in targets:
                (m.toggle if toggle else m.play)(name, samples_at(m.sr))
        except Exception as e:  # noqa: BLE001
            self._error(f"Could not play {name}:\n{e}")

    # ---------------------------------------------------------------- type to speak
    def _current_voice_label(self) -> str:
        if self.audio_tab == 1:
            item = self.voice_list.currentItem()
            if item and item.flags() & Qt.ItemIsSelectable:
                return item.text()
        return "Clean" if self.fx_preset == "clean" else self.fx_preset.capitalize()

    def _open_type(self):
        from . import tts
        why = tts.available()
        if why:
            return self._error(why)
        self.type_popup.open(self._current_voice_label(),
                             "" if self.engine else "Not live: only you will hear it. Enter to speak · Esc to close")

    def _speak(self, text: str):
        from . import tts
        from .soundboard import _resample
        ai_voice = None
        if self.audio_tab == 1:
            item = self.voice_list.currentItem()
            if item and item.flags() & Qt.ItemIsSelectable:
                ai_voice = item.text()
        preset = self.fx_preset
        gender = tts.guess_gender(ai_voice) if ai_voice else None

        def work():
            x = tts.synthesize(text, gender or "Female")
            if ai_voice:
                from .ai import assets, preview
                return preview.get_previewer().convert(assets.find_voice(ai_voice)[0], x, 0)
            return (tts.apply_effect(x, preset) if preset != "clean" else x), tts.TTS_SR

        def done(res):
            y, sr = res
            self._play_samples("type to speak", lambda out_sr: _resample(y, sr, out_sr), toggle=False)

        task = Task(work, self)
        task.done.connect(done)
        task.failed.connect(lambda e: self._error(f"Type to speak failed:\n{e}"))
        task.finished.connect(lambda: self.tts_tasks.remove(task) if task in self.tts_tasks else None)
        self.tts_tasks.append(task)
        task.start()

    def _stop_clips(self):
        for m in (self.sb_mix, self.sb_local.mixer if self.sb_local else None):
            if m is not None:
                m.stop_all()

    def _sb_volume(self, v: float):
        for m in (self.sb_mix, self.sb_local.mixer if self.sb_local else None):
            if m is not None:
                m.volume = v

    # ---------------------------------------------------------------- hotkeys + push-to-talk
    def _ptt_gated(self) -> bool:
        """True while push-to-talk is on and the key isn't held: send silence."""
        return self.cfg.value("hotkeys/ptt_on", "false") == "true" and not self.ptt_held

    def _apply_mute(self, eng=None):
        eng = eng or self.engine
        if eng is not None:
            eng.muted = self.mute.isChecked() or self._ptt_gated()

    def _on_ptt(self, held: bool):
        self.ptt_held = held
        self._apply_mute()

    def _load_hotkeys(self):
        from .ai import assets
        from .soundboard import list_clips
        acts = (["tts:open"] + [f"voice:{v}" for v in assets.list_voices()] + [f"preset:{p}" for p in PRESETS]
                + [f"clip:{c.name}" for c in list_clips()])
        bindings = {a: self.cfg.value(f"hotkeys/{a}", "") or "" for a in acts}
        self.hk.set_bindings(bindings, self.cfg.value("hotkeys/ptt", "") or "")
        self._apply_mute()

    def _open_hotkeys(self):
        from .ai import assets
        from .hotkeys_dialog import HotkeysDialog
        from .soundboard import list_clips
        dlg = HotkeysDialog(self.cfg, self.hk, assets.list_voices(), self,
                            clips=[c.name for c in list_clips()])
        dlg.saved.connect(self._load_hotkeys)
        dlg.exec()

    def _hotkey_action(self, act: str):
        kind, name = act.split(":", 1)
        if kind == "tts":
            self._open_type()
        elif kind == "clip":
            self._play_clip(name)
        elif kind == "preset" and name in self.fx_buttons:
            self.fx_buttons[name].setChecked(True)
            self.fx_preset = name
            if self.tabs.currentIndex() != 0:
                self.tabs.setCurrentIndex(0)     # restarts in effects mode if live
            else:
                self._pick_fx(name)
        elif kind == "voice":
            items = self.voice_list.findItems(name, Qt.MatchExactly)
            if not items or self._task_running():
                return
            if self.tabs.currentIndex() != 1:
                self.voice_list.blockSignals(True)
                self.voice_list.setCurrentItem(items[0])
                self.voice_list.blockSignals(False)
                self.tabs.setCurrentIndex(1)     # restarts with this voice if live
            else:
                self.voice_list.setCurrentItem(items[0])  # live: switches voice

    def _tick(self):
        playing = set()
        for m in (self.sb_mix, self.sb_local.mixer if self.sb_local else None):
            if m is not None:
                playing |= m.playing
        self.sb_tab.show_playing(playing)
        eng = self.engine
        if not eng or not self.start.isEnabled():
            return
        def level(peak):
            db = 20 * math.log10(max(peak, 1e-5))
            return int(max(0, min(100, (db + 60) / 60 * 100)))
        self.meter.setValue(level(eng.peak_out))
        self.meter_in.setValue(level(getattr(eng, "peak_in", 0.0)))
        state = "off" if self._ptt_gated() else "live"
        self.pill.setText("HOLD TO TALK" if state == "off" else f"ON AIR  {eng.latency_ms:.0f} ms")
        if self.pill.property("state") != state:
            self._restyle(self.pill, "state", state)
        if self.mode == "fx":
            self.status.setText(f"{eng.preset}   cpu {eng.cpu_load * 100:.1f}%   dropouts {eng.xruns}")
        else:
            warn = "   near limit: try Fast mode" if eng.load > 0.8 else ""
            err = f"   error: {eng.last_error}" if eng.last_error else ""
            self.status.setText(f"gpu {eng.infer_ms:.0f} ms   load {eng.load * 100:.0f}%   "
                                f"dropouts {eng.xruns}{warn}{err}")

    # ---------------------------------------------------------------- persistence
    def closeEvent(self, event):
        self.hk.stop()
        self.type_popup.close()
        for t in list(self.tts_tasks):
            t.wait(5000)
        if self.sb_local is not None:
            self.sb_local.close()
        c = self.cfg
        c.setValue("input", self.mic.currentText())
        c.setValue("output", self.out.currentText())
        c.setValue("gate", self.gate.value())
        c.setValue("gate_on", "true" if self.gate_on.isChecked() else "false")
        c.setValue("monitor", "true" if self.mon_on.isChecked() else "false")
        c.setValue("phones", self.phones.currentText())
        c.setValue("pitch", self.pitch.value())
        c.setValue("formant", self.formant.value())
        c.setValue("index", self.index.value())
        c.setValue("quality", self.quality.currentText())
        c.setValue("tab", self.tabs.currentIndex())
        c.setValue("audio_tab", self.audio_tab)
        c.setValue("sounds/volume", self.sb_tab.vol.value())
        if self.voice_list.currentItem():
            c.setValue("voice", self.voice_list.currentItem().text())
        if self.task and self.task.isRunning():
            self.task.wait(10000)
        store = getattr(self, "store", None)
        if store is not None and store.worker and store.worker.isRunning():
            store.worker.wait(30000)
        self._detach_monitor()
        if self.engine:
            self.engine.stop()
        super().closeEvent(event)


def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI Variable Text", 10) if sys.platform == "win32" else QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    if sys.platform == "win32":  # own taskbar entry/icon instead of python.exe's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("voicefork.app")
        except Exception:  # noqa: BLE001
            pass
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
