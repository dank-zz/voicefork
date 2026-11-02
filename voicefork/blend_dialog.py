"""'Blend voices' window: mix two voices, preview with your recording, save as a new voice."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QSlider, QSpinBox, QVBoxLayout,
)

from .voice_store import Worker


class BlendDialog(QDialog):
    saved = Signal(str)  # name of the new voice

    def __init__(self, voices: list[str], pitch: int, play, parent=None):
        super().__init__(parent)
        from .gui import field, section
        self.setWindowTitle("Blend voices")
        self.resize(480, 360)
        self.play = play          # callable(samples, sr) that plays on your headphones
        self.worker: Worker | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(section("Blend two voices into a new one"))
        note = QLabel("The new voice belongs to nobody: it's a mix of both. Voices must be the same kind "
                      "of model (all the starter voices are).")
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        self.a, self.b = QComboBox(), QComboBox()
        for c in (self.a, self.b):
            c.addItems(voices)
        if len(voices) > 1:
            self.b.setCurrentIndex(1)
        form.addRow(field("Voice A"), self.a)
        form.addRow(field("Voice B"), self.b)

        mix_row = QHBoxLayout()
        self.mix = QSlider(Qt.Horizontal)
        self.mix.setRange(0, 100)
        self.mix.setValue(50)
        self.mix_lab = QLabel("")
        self.mix_lab.setObjectName("value")
        self.mix_lab.setMinimumWidth(110)
        self.mix_lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        mix_row.addWidget(self.mix, 1)
        mix_row.addWidget(self.mix_lab)
        form.addRow(field("Mix"), mix_row)

        self.pitch = QSpinBox()
        self.pitch.setRange(-24, 24)
        self.pitch.setSuffix(" st")
        self.pitch.setValue(pitch)
        form.addRow(field("Preview pitch"), self.pitch)
        self.name = QLineEdit()
        form.addRow(field("Name"), self.name)
        lay.addLayout(form)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.hide()
        lay.addWidget(self.busy)
        self.status = QLabel("")
        self.status.setObjectName("mono")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        pv = QPushButton("Preview")
        pv.setToolTip("Hear your saved recording (from Get voices) through this mix")
        pv.clicked.connect(self._preview)
        save = QPushButton("Save voice")
        save.setObjectName("start")
        save.clicked.connect(self._save)
        row.addWidget(pv)
        row.addWidget(save)
        lay.addLayout(row)

        self._user_named = False
        self.name.textEdited.connect(lambda _: setattr(self, "_user_named", True))
        for sig in (self.a.currentTextChanged, self.b.currentTextChanged, self.mix.valueChanged):
            sig.connect(self._update_labels)
        self._update_labels()

    # ------------------------------------------------------------------
    @staticmethod
    def _short(name: str) -> str:
        return name.split("(")[0].replace("Female - ", "F ").replace("Male - ", "M ").strip()

    def _update_labels(self, *_):
        m = self.mix.value()
        self.mix_lab.setText(f"{100 - m}% A · {m}% B")
        if not self._user_named:
            self.name.setText(f"Blend - {self._short(self.a.currentText())} + {self._short(self.b.currentText())}"
                              f" {100 - m}-{m}")

    def _inputs(self):
        from .ai import assets
        a, b = self.a.currentText(), self.b.currentText()
        if not a or not b or a == b:
            raise ValueError("Pick two different voices.")
        return assets.find_voice(a)[0], assets.find_voice(b)[0], self.mix.value() / 100

    def _run(self, text, fn, done):
        if self.worker and self.worker.isRunning():
            return
        self.status.setText(text)
        self.busy.show()
        self.worker = Worker(fn, self)
        self.worker.done.connect(lambda r: (self.busy.hide(), done(r)))
        self.worker.failed.connect(lambda e: (self.busy.hide(), self.status.setText(""),
                                              QMessageBox.warning(self, "Blend voices", e)))
        self.worker.start()

    def _preview(self):
        from .ai import blend, preview
        try:
            pa, pb, mix = self._inputs()
        except ValueError as e:
            self.status.setText(str(e))
            return
        clip = preview.load_demo()
        if clip is None:
            self.status.setText("Record your voice first: Get voices → Record my voice.")
            return
        pitch = self.pitch.value()

        def work():
            path = blend.write(blend.blend(pa, pb, mix), blend.preview_path())
            return preview.get_previewer().convert(path, clip, pitch)

        self._run("Mixing and converting your recording …", work,
                  lambda r: (self.play(*r), self.status.setText("Playing preview.")))

    def _save(self):
        from .ai import blend
        try:
            pa, pb, mix = self._inputs()
        except ValueError as e:
            self.status.setText(str(e))
            return
        name = self.name.text().strip()
        if not name:
            self.status.setText("Give the voice a name.")
            return

        def work():
            return blend.save_as_voice(blend.blend(pa, pb, mix), name)

        def done(path):
            self.status.setText(f"Saved: {path.parent.name}")
            self.saved.emit(path.parent.name)

        self._run("Saving …", work, done)
