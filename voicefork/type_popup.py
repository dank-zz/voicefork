"""Small always-on-top typing box for Type to speak, opened with a hotkey."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget


def force_foreground(widget: QWidget):
    """Windows only lets the foreground app hand out focus. Borrow the foreground
    thread's input for a moment so the box really gets the keyboard over a game."""
    widget.raise_()
    widget.activateWindow()
    if sys.platform != "win32":
        return
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = int(widget.winId())
        fg = u.GetForegroundWindow()
        fg_thread = u.GetWindowThreadProcessId(fg, None)
        me = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_thread and fg_thread != me:
            u.AttachThreadInput(me, fg_thread, True)
            u.SetForegroundWindow(hwnd)
            u.BringWindowToTop(hwnd)
            u.AttachThreadInput(me, fg_thread, False)
        else:
            u.SetForegroundWindow(hwnd)
    except Exception:  # noqa: BLE001 - best effort; Qt's own activation above still applies
        pass


class TypePopup(QWidget):
    speak = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.history: list[str] = []
        self._hist_pos = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        box = QFrame()
        box.setObjectName("popup")
        box.setStyleSheet("QFrame#popup { background: #17181b; border: 1px solid #3a3c42; border-radius: 10px; }")
        outer.addWidget(box)
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(4)
        row = QHBoxLayout()
        from .gui import Logo
        row.addWidget(Logo(16))
        self.edit = QLineEdit()
        self.edit.setStyleSheet("QLineEdit { background: transparent; border: none; font-size: 15px; padding: 4px; }")
        self.edit.returnPressed.connect(self._enter)
        row.addWidget(self.edit, 1)
        v.addLayout(row)
        self.info = QLabel("")
        self.info.setObjectName("mono")
        v.addWidget(self.info)
        self.setFixedWidth(560)

    def open(self, voice_label: str, status: str = ""):
        self.edit.setPlaceholderText(f"Type and press Enter to speak as {voice_label}")
        self.info.setText(status or "Enter to speak · ↑ for history · Esc to close")
        screen = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center()) \
            or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        self.adjustSize()
        self.move(g.center().x() - self.width() // 2, g.top() + int(g.height() * 0.18))
        self.show()
        force_foreground(self)
        self.edit.setFocus()
        self.edit.selectAll()

    def set_status(self, text: str):
        self.info.setText(text)

    def _enter(self):
        text = self.edit.text().strip()
        if not text:
            self.hide()
            return
        self.history.append(text)
        self._hist_pos = len(self.history)
        self.edit.clear()
        self.speak.emit(text)
        self.hide()  # back to the game right away; speech plays when ready

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
        elif e.key() in (Qt.Key_Up, Qt.Key_Down) and self.history:
            self._hist_pos = max(0, min(len(self.history), self._hist_pos + (-1 if e.key() == Qt.Key_Up else 1)))
            self.edit.setText(self.history[self._hist_pos] if self._hist_pos < len(self.history) else "")
        else:
            super().keyPressEvent(e)
