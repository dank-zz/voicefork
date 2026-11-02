"""'Hotkeys' window: assign push-to-talk and one key per voice / effect preset."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .hotkeys import pretty, qt_key_name, qt_mouse_name
from .presets import PRESETS


class KeyCapture(QPushButton):
    """Click, then press a key (or mouse side button) to bind it. Esc cancels."""
    captured = Signal(str)
    capturing = Signal(bool)

    def __init__(self, binding: str = ""):
        super().__init__()
        self.binding = binding
        self._active = False
        self.setMinimumWidth(130)
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self._begin)
        self._show()

    def _show(self):
        self.setText("press a key…" if self._active else pretty(self.binding))

    def _begin(self):
        self._active = True
        self._show()
        self.grabKeyboard()
        self.grabMouse()
        self.capturing.emit(True)

    def _end(self, binding: str | None):
        self._active = False
        self.releaseKeyboard()
        self.releaseMouse()
        if binding is not None:
            self.binding = binding
            self.captured.emit(binding)
        self._show()
        self.capturing.emit(False)

    def set_binding(self, binding: str):
        self.binding = binding
        self._show()

    def keyPressEvent(self, e):
        if not self._active:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key_Escape:
            return self._end(None)
        name = qt_key_name(e)
        if name:
            self._end(name)

    def mousePressEvent(self, e):
        if not self._active:
            return super().mousePressEvent(e)
        name = qt_mouse_name(e)
        if name:
            self._end(name)
        elif e.button() == Qt.LeftButton and not self.rect().contains(e.position().toPoint()):
            self._end(None)  # clicked elsewhere: cancel


class HotkeysDialog(QDialog):
    saved = Signal()

    def __init__(self, cfg, manager, voices: list[str], parent=None, clips: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Hotkeys")
        self.resize(460, 620)
        self.cfg, self.manager = cfg, manager
        self.captures: dict[str, KeyCapture] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        from .gui import section, switch  # shared look
        lay.addWidget(section("Push-to-talk"))
        row = QHBoxLayout()
        self.ptt_on = switch("Only send my voice while holding", cfg.value("hotkeys/ptt_on", "false") == "true")
        row.addWidget(self.ptt_on, 1)
        row.addWidget(self._capture("ptt"))
        lay.addLayout(row)
        hint = QLabel("Works in games too. Mouse side buttons can be used.")
        hint.setObjectName("muted")
        lay.addWidget(hint)

        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        r = 0
        for title, ids in (("Type to speak", ["tts:open"]),
                           ("AI voices", [f"voice:{v}" for v in voices]),
                           ("Effects", [f"preset:{p}" for p in PRESETS]),
                           ("Soundboard", [f"clip:{c}" for c in clips or []])):
            grid.addWidget(section(title), r, 0, 1, 3)
            r += 1
            if not ids:
                none = QLabel("No clips yet." if title == "Soundboard" else "No voices installed yet.")
                none.setObjectName("muted")
                grid.addWidget(none, r, 0, 1, 3)
                r += 1
            for act in ids:
                name = act.split(":", 1)[1]
                lab = QLabel("Open typing box" if act == "tts:open"
                             else name if act.startswith(("voice:", "clip:")) else name.capitalize())
                lab.setObjectName("field")
                clear = QPushButton("Clear")
                clear.clicked.connect(lambda _=False, a=act: self._set(a, ""))
                grid.addWidget(lab, r, 0)
                grid.addWidget(self._capture(act), r, 1)
                grid.addWidget(clear, r, 2)
                r += 1
            grid.setRowMinimumHeight(r, 10)
            r += 1
        grid.setColumnStretch(0, 1)
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        lay.addWidget(scroll, 1)

        self.note = QLabel("")
        self.note.setObjectName("mono")
        lay.addWidget(self.note)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("start")
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        lay.addLayout(bottom)

    def _capture(self, act: str) -> KeyCapture:
        cap = KeyCapture(self.cfg.value(f"hotkeys/{act}", "") or "")
        cap.captured.connect(lambda b, a=act: self._set(a, b))
        cap.capturing.connect(lambda on: setattr(self.manager, "paused", on))
        self.captures[act] = cap
        return cap

    def _set(self, act: str, binding: str):
        # one key, one job: take it away from whatever had it
        if binding:
            for other, cap in self.captures.items():
                if other != act and cap.binding == binding:
                    cap.set_binding("")
                    self.note.setText(f"{pretty(binding)} moved from {other.split(':', 1)[1]}")
        self.captures[act].set_binding(binding)

    def accept(self):
        self.cfg.setValue("hotkeys/ptt_on", "true" if self.ptt_on.isChecked() else "false")
        for act, cap in self.captures.items():
            self.cfg.setValue(f"hotkeys/{act}", cap.binding)
        self.manager.paused = False
        self.saved.emit()
        super().accept()

    def reject(self):
        self.manager.paused = False
        super().reject()
