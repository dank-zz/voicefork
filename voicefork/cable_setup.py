"""'Set up the virtual mic' window: explains the one-time cable install and checks for it."""
from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .devices import has_virtual_cable, rescan, setup_info


class CableSetup(QDialog):
    """Shown when no virtual cable exists. found() fires once one shows up after "Check again".
    With going_live=True there is also a "Go live anyway" button (accept() = start without it)."""
    found = Signal()

    def __init__(self, going_live: bool = False, parent=None):
        super().__init__(parent)
        from .gui import section
        what, self.url, steps = setup_info()
        self.setWindowTitle("Set up the virtual mic")
        self.resize(500, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section("ONE-TIME SETUP, ABOUT A MINUTE"))
        why = QLabel("Discord, OBS and games can only use a microphone your computer knows about. "
                     f"{what} is a free virtual mic: Voicefork plays into it, and the other app "
                     "listens to it.")
        why.setObjectName("muted")
        why.setWordWrap(True)
        lay.addWidget(why)

        for i, s in enumerate(steps, 1):
            row = QLabel(f"{i}.  {s}")
            row.setWordWrap(True)
            lay.addWidget(row)

        self.result_label = QLabel("Without it you can still try voices and hear yourself (Monitor).")
        self.result_label.setObjectName("muted")
        self.result_label.setWordWrap(True)
        lay.addWidget(self.result_label)

        btns = QHBoxLayout()
        dl = QPushButton(f"Download {what}")
        dl.setObjectName("start")
        dl.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.url)))
        btns.addWidget(dl)
        again = QPushButton("Check again")
        again.clicked.connect(self.check)
        btns.addWidget(again)
        btns.addStretch(1)
        if going_live:
            anyway = QPushButton("Go live anyway")
            anyway.setToolTip("Starts on your current output. Others won't hear you in Discord.")
            anyway.clicked.connect(self.accept)
            btns.addWidget(anyway)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        lay.addLayout(btns)

    def check(self) -> bool:
        import sounddevice as sd
        try:
            rescan()
            ok = has_virtual_cable(sd.query_devices())
        except Exception as e:  # noqa: BLE001
            self.result_label.setText(f"Couldn't list audio devices: {e}")
            return False
        if ok:
            self.result_label.setText("Found it. You're set: close this and hit Go live.")
            self.found.emit()
        else:
            self.result_label.setText("Not found yet. If you just installed it, restart your PC first.")
        return ok
