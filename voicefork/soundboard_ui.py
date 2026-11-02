"""Soundboard tab: clip grid, drag-and-drop, add, record, rename/delete."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from . import soundboard as sbm

MAX_RECORD_S = 30


class SoundboardTab(QWidget):
    play = Signal(str)          # clip name
    stop_all = Signal()
    volume = Signal(float)
    changed = Signal()          # clips added/renamed/removed

    def __init__(self, cfg, mic_device):
        super().__init__()
        from .gui import section
        self.cfg = cfg
        self.mic_device = mic_device          # callable -> current mic index
        self.tiles: dict[str, QPushButton] = {}
        self._rec = None
        self.setAcceptDrops(True)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(section("Soundboard"))
        top.addStretch(1)
        self.rec_btn = QPushButton("Record")
        self.rec_btn.setToolTip(f"Record a clip from your mic (up to {MAX_RECORD_S} s). Click again to stop.")
        self.rec_btn.clicked.connect(self._toggle_record)
        add = QPushButton("Add clip")
        add.clicked.connect(self._add)
        folder = QPushButton("Folder")
        folder.setToolTip("Open the sounds folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(sbm.sounds_dir()))))
        stop = QPushButton("Stop all")
        stop.clicked.connect(self.stop_all.emit)
        for b in (self.rec_btn, add, folder, stop):
            top.addWidget(b)
        v.addLayout(top)

        vol_row = QHBoxLayout()
        from .gui import field
        vol_row.addWidget(field("Volume"))
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 150)
        self.vol.setValue(int(cfg.value("sounds/volume", 100)))
        self.vol.valueChanged.connect(lambda x: self.volume.emit(x / 100))
        vol_row.addWidget(self.vol, 1)
        v.addLayout(vol_row)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidget(self.grid_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        v.addWidget(scroll, 1)
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._rec_tick)
        self.refresh()

    # ---------------------------------------------------------------- grid
    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.tiles = {}
        clips = sbm.list_clips()
        for i, clip in enumerate(clips):
            b = QPushButton(f"{clip.name}\n{clip.seconds:.1f} s")
            b.setObjectName("tile")
            b.setCheckable(True)
            b.setMinimumHeight(58)
            b.setToolTip("Click to play, click again to stop. Right-click to rename or delete.")
            b.clicked.connect(lambda _=False, n=clip.name: self._clicked(n))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, c=clip, btn=b: self._menu(c, btn, pos))
            self.grid.addWidget(b, i // 3, i % 3)
            self.tiles[clip.name] = b
        self.grid.setRowStretch(len(clips) // 3 + 1, 1)
        self.hint.setText("Drop audio files here (wav, mp3, ogg, flac), use Add clip, or Record."
                          if not clips else "Tip: give clips hotkeys under Hotkeys.")

    def _clicked(self, name):
        self.tiles[name].setChecked(False)   # the playing state comes from the mixer, see show_playing
        self.play.emit(name)

    def show_playing(self, playing: set[str]):
        for name, b in self.tiles.items():
            on = name in playing
            if b.isChecked() != on:
                b.setChecked(on)

    def _menu(self, clip, btn, pos):
        m = QMenu(self)
        ren = m.addAction("Rename")
        dele = m.addAction("Delete")
        act = m.exec(btn.mapToGlobal(pos))
        if act is ren:
            new, ok = QInputDialog.getText(self, "Rename clip", "Name:", text=clip.name)
            if ok and new.strip():
                sbm.rename_clip(clip, new.strip())
                self.refresh()
                self.changed.emit()
        elif act is dele:
            if QMessageBox.question(self, "Delete clip", f"Delete '{clip.name}'?") == QMessageBox.Yes:
                sbm.delete_clip(clip)
                self.refresh()
                self.changed.emit()

    # ---------------------------------------------------------------- adding
    def _import(self, paths):
        added, errors = 0, []
        for p in paths:
            try:
                sbm.import_file(Path(p))
                added += 1
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
        if added:
            self.refresh()
            self.changed.emit()
        if errors:
            QMessageBox.warning(self, "Soundboard", "\n".join(errors[:5]))

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add clips", str(Path.home() / "Downloads"),
            "Audio (" + " ".join(f"*{e}" for e in sbm.AUDIO_TYPES) + ")")
        if files:
            self._import(files)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(sbm.AUDIO_TYPES)
                                          for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        self._import([u.toLocalFile() for u in e.mimeData().urls()
                      if u.toLocalFile().lower().endswith(sbm.AUDIO_TYPES)])

    # ---------------------------------------------------------------- recording
    def _toggle_record(self):
        if self._rec is None:
            self._start_record()
        else:
            self._stop_record()

    def _start_record(self):
        import sounddevice as sd
        dev = self.mic_device()
        try:
            rate = int(sd.query_devices(dev, "input")["default_samplerate"])
            chunks: list[np.ndarray] = []
            stream = sd.InputStream(device=dev, samplerate=rate, channels=1, dtype="float32",
                                    callback=lambda d, *_: chunks.append(d[:, 0].copy()))
            stream.start()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Soundboard", f"Could not open the microphone:\n{e}")
            return
        self._rec = (stream, chunks, rate, 0.0)
        self.rec_btn.setText("Stop  0.0 s")
        self._rec_timer.start(100)

    def _rec_tick(self):
        stream, chunks, rate, t = self._rec
        t += 0.1
        self._rec = (stream, chunks, rate, t)
        self.rec_btn.setText(f"Stop  {t:.1f} s")
        if t >= MAX_RECORD_S:
            self._stop_record()

    def _stop_record(self):
        stream, chunks, rate, _ = self._rec
        self._rec = None
        self._rec_timer.stop()
        self.rec_btn.setText("Record")
        stream.stop()
        stream.close()
        audio = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
        name, ok = QInputDialog.getText(self, "Save clip", "Name:", text="recording")
        if not ok:
            return
        try:
            sbm.save_recording(audio, rate, name.strip() or "recording")
        except ValueError as e:
            QMessageBox.warning(self, "Soundboard", str(e))
            return
        self.refresh()
        self.changed.emit()
