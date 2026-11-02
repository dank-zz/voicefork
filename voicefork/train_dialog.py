"""'Make your own voice' window: record (or import) ~10 minutes, then train."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QProgressBar,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .ai import assets
from .ai import training as tr
from .ai.training import prompts

def draft_dir() -> Path:
    d = assets.home() / "recordings" / "_draft"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TrainWorker(QThread):
    progress = Signal(object)    # training.Progress
    line = Signal(str)
    done = Signal(object)        # Path
    failed = Signal(str)

    def __init__(self, name, preset, folder, parent=None):
        super().__init__(parent)
        self.job = tr.TrainJob(name, preset, report=self.progress.emit, log=self.line.emit)
        self.folder = folder

    def run(self):
        try:
            self.done.emit(self.job.run(self.folder))
        except tr.Cancelled:
            self.failed.emit("")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class TrainDialog(QDialog):
    trained = Signal(str)     # new voice name

    def __init__(self, mic_device, is_live, parent=None):
        super().__init__(parent)
        from .gui import Segmented, field, section, switch
        self.setWindowTitle("Make your own voice")
        self.resize(620, 640)
        self.mic_device, self.is_live = mic_device, is_live
        self.prompts = prompts()
        self.prompt_i = 0
        self.rec = None
        self.worker: TrainWorker | None = None
        self._saved = 0.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)

        # ---------------- page 1: recordings
        p1 = QWidget()
        v = QVBoxLayout(p1)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(section("1 · Record your voice"))
        tip = QLabel("Use the mic you'll talk with, in a quiet room. Speak naturally, with some variety. "
                     "10 minutes gives the best voice; 2 minutes is the minimum. Your recordings are kept, "
                     "so you can do this over several sessions.")
        tip.setWordWrap(True)
        tip.setObjectName("muted")
        v.addWidget(tip)

        self.prompt = QLabel("")
        self.prompt.setWordWrap(True)
        self.prompt.setAlignment(Qt.AlignCenter)
        self.prompt.setMinimumHeight(90)
        self.prompt.setStyleSheet("font-size: 20px; padding: 12px; border: 1px solid #25272c; border-radius: 8px;")
        v.addWidget(self.prompt)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        v.addWidget(self.level)

        row = QHBoxLayout()
        self.rec_btn = QPushButton("Start recording")
        self.rec_btn.setObjectName("start")
        self.rec_btn.clicked.connect(self._toggle_rec)
        self.next_btn = QPushButton("Next sentence  (Space)")
        self.next_btn.clicked.connect(self._next_prompt)
        imp = QPushButton("Import audio files")
        imp.clicked.connect(self._import)
        row.addWidget(self.rec_btn)
        row.addWidget(self.next_btn)
        row.addStretch(1)
        row.addWidget(imp)
        v.addLayout(row)

        tot = QHBoxLayout()
        self.total_lab = QLabel("")
        self.total_lab.setObjectName("value")
        self.total_bar = QProgressBar()
        self.total_bar.setRange(0, tr.GOOD_SECONDS)
        self.total_bar.setTextVisible(False)
        tot.addWidget(field("Recorded"))
        tot.addWidget(self.total_bar, 1)
        tot.addWidget(self.total_lab)
        v.addLayout(tot)

        self.takes = QListWidget()
        self.takes.setMaximumHeight(110)
        v.addWidget(self.takes)
        rm = QPushButton("Remove selected take")
        rm.clicked.connect(self._remove_take)
        v.addWidget(rm, alignment=Qt.AlignLeft)

        v.addWidget(section("2 · Name and consent"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Voice name, e.g. My voice")
        v.addWidget(self.name)
        self.consent = switch("This is my own voice, or I have the person's permission to make this voice", False)
        v.addWidget(self.consent)
        nav = QHBoxLayout()
        nav.addStretch(1)
        self.to_train = QPushButton("Next: train")
        self.to_train.setObjectName("start")
        self.to_train.clicked.connect(self._go_train)
        nav.addWidget(self.to_train)
        v.addLayout(nav)
        self.pages.addWidget(p1)

        # ---------------- page 2: training
        p2 = QWidget()
        t = QVBoxLayout(p2)
        t.setContentsMargins(0, 0, 0, 0)
        t.setSpacing(12)
        t.addWidget(section("3 · Train"))
        self.quality = Segmented(list(tr.PRESETS), "Standard")
        t.addWidget(self.quality)
        est = QLabel("  ·  ".join(f"{k}: about {m} min" for k, (_, m) in tr.PRESETS.items())
                     + "\nLonger training = a more natural voice. You can keep using your PC, "
                     "but games will be slower while it trains.")
        est.setObjectName("muted")
        est.setWordWrap(True)
        t.addWidget(est)
        self.stage = QLabel("Ready.")
        self.stage.setStyleSheet("font-size: 16px; font-weight: 600;")
        t.addWidget(self.stage)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        t.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setObjectName("mono")
        t.addWidget(self.detail)
        self.logline = QLabel("")
        self.logline.setObjectName("mono")
        self.logline.setWordWrap(True)
        t.addWidget(self.logline)
        t.addStretch(1)
        nav2 = QHBoxLayout()
        self.back = QPushButton("Back")
        self.back.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.cancel_btn = QPushButton("Cancel training")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        self.start_btn = QPushButton("Start training")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self._start)
        nav2.addWidget(self.back)
        nav2.addStretch(1)
        nav2.addWidget(self.cancel_btn)
        nav2.addWidget(self.start_btn)
        t.addLayout(nav2)
        self.pages.addWidget(p2)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)
        self._show_prompt()
        self._refresh_takes()

    # ------------------------------------------------------------- recording
    def _show_prompt(self):
        self.prompt.setText(self.prompts[self.prompt_i % len(self.prompts)])

    def _next_prompt(self):
        self.prompt_i += 1
        self._show_prompt()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and self.pages.currentIndex() == 0 and not self.name.hasFocus():
            self._next_prompt()
        else:
            super().keyPressEvent(e)

    def _toggle_rec(self):
        if self.rec is None:
            import sounddevice as sd
            dev = self.mic_device()
            try:
                rate = int(sd.query_devices(dev, "input")["default_samplerate"])
                chunks: list[np.ndarray] = []
                state = {"peak": 0.0}

                def cb(d, *_):
                    x = d[:, 0].copy()
                    chunks.append(x)
                    state["peak"] = float(np.max(np.abs(x)))

                stream = sd.InputStream(device=dev, samplerate=rate, channels=1, dtype="float32", callback=cb)
                stream.start()
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Make your own voice", f"Could not open the microphone:\n{e}")
                return
            self.rec = (stream, chunks, rate, state, time.time())
            self.rec_btn.setText("Stop recording")
        else:
            self._stop_rec()

    def _stop_rec(self):
        import soundfile as sf
        stream, chunks, rate, _, _ = self.rec
        self.rec = None
        stream.stop()
        stream.close()
        self.rec_btn.setText("Start recording")
        self.level.setValue(0)
        if chunks:
            audio = np.concatenate(chunks)
            if len(audio) > rate:  # skip accidental sub-second takes
                sf.write(str(draft_dir() / time.strftime("take_%Y%m%d_%H%M%S.wav")), audio, rate, subtype="FLOAT")
        self._refresh_takes()

    def _tick(self):
        if self.rec is not None:
            stream, chunks, rate, state, t0 = self.rec
            db = 20 * np.log10(max(state["peak"], 1e-5))
            self.level.setValue(int(max(0, min(100, (db + 60) / 60 * 100))))
            live = time.time() - t0
            self._show_total(self._saved + live)

    def _import(self):
        import soundfile as sf
        files, _ = QFileDialog.getOpenFileNames(self, "Import recordings", str(Path.home()),
                                                "Audio (*.wav *.mp3 *.flac *.ogg *.m4a)")
        bad = []
        for f in files:
            try:
                data, sr = sf.read(f, dtype="float32", always_2d=True)
                sf.write(str(draft_dir() / f"import_{Path(f).stem[:40]}.wav"), data.mean(axis=1), sr, subtype="FLOAT")
            except Exception as e:  # noqa: BLE001
                bad.append(f"{Path(f).name}: {e}")
        if bad:
            QMessageBox.warning(self, "Make your own voice", "\n".join(bad[:5]))
        self._refresh_takes()

    def _remove_take(self):
        item = self.takes.currentItem()
        if item and QMessageBox.question(self, "Remove take", f"Delete {item.text().split('  ')[0]}?") == QMessageBox.Yes:
            (draft_dir() / item.data(Qt.UserRole)).unlink(missing_ok=True)
            self._refresh_takes()

    def _refresh_takes(self):
        import soundfile as sf
        self.takes.clear()
        total = 0.0
        for f in sorted(draft_dir().glob("*.wav")):
            try:
                d = sf.info(str(f)).duration
            except Exception:  # noqa: BLE001
                continue
            total += d
            self.takes.addItem(f"{f.stem}  ·  {d / 60:.1f} min")
            self.takes.item(self.takes.count() - 1).setData(Qt.UserRole, f.name)
        self._saved = total
        self._show_total(total)

    def _show_total(self, seconds):
        self.total_bar.setValue(int(min(seconds, tr.GOOD_SECONDS)))
        self.total_lab.setText(f"{seconds / 60:4.1f} / 10 min")

    # ------------------------------------------------------------- training
    def _go_train(self):
        if self.rec is not None:
            self._stop_rec()
        if self._saved < tr.MIN_SECONDS:
            return QMessageBox.information(self, "Make your own voice",
                                           f"Record at least {tr.MIN_SECONDS // 60} minutes first (10 is best).")
        if not self.name.text().strip():
            return QMessageBox.information(self, "Make your own voice", "Give the voice a name.")
        if not self.consent.isChecked():
            return QMessageBox.information(self, "Make your own voice",
                                           "Please confirm it's your voice or that you have permission.")
        self.pages.setCurrentIndex(1)

    def _start(self):
        if self.is_live():
            return QMessageBox.information(self, "Make your own voice",
                                           "Stop the voice changer first: training needs the whole GPU.")
        if self.worker and self.worker.isRunning():
            return
        self.worker = TrainWorker(self.name.text().strip(), self.quality.currentText(), draft_dir(), self)
        self.worker.progress.connect(self._progress)
        self.worker.line.connect(lambda s: self.logline.setText(s[-160:]))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.start_btn.hide()
        self.back.setEnabled(False)
        self.cancel_btn.show()
        self.stage.setText("Starting …")
        self.worker.start()

    def _progress(self, p):
        self.stage.setText(p.stage)
        self.bar.setValue(int(p.fraction * 1000))
        eta = f"   ·   about {p.eta_s / 60:.0f} min left" if p.eta_s else ""
        self.detail.setText(f"{p.detail}{eta}")

    def _cancel(self):
        if self.worker and QMessageBox.question(self, "Cancel training", "Stop training? Your recordings are kept.") \
                == QMessageBox.Yes:
            self.cancel_btn.setEnabled(False)
            self.stage.setText("Stopping …")
            self.worker.job.cancel()

    def _reset_buttons(self):
        self.cancel_btn.hide()
        self.cancel_btn.setEnabled(True)
        self.start_btn.show()
        self.back.setEnabled(True)

    def _failed(self, msg):
        self._reset_buttons()
        self.bar.setValue(0)
        if not msg:
            self.stage.setText("Cancelled. Your recordings are kept.")
            return
        self.stage.setText("Training failed.")
        QMessageBox.warning(self, "Make your own voice", msg[-1500:])

    def _done(self, dest: Path):
        # keep the recordings with the voice's name so it can be retrained later
        keep = tr.recordings_dir(dest.name)
        for f in draft_dir().glob("*.wav"):
            shutil.move(str(f), keep / f.name)
        self._reset_buttons()
        self.start_btn.hide()
        self.stage.setText(f"Your voice '{dest.name}' is ready.")
        self.detail.setText("It's now in your voice list. Try it with Go live.")
        self.trained.emit(dest.name)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "Training is running",
                                    "Training is still running. Cancel it and close?") != QMessageBox.Yes:
                e.ignore()
                return
            self.worker.job.cancel()
            self.worker.wait(15000)
        if self.rec is not None:
            self._stop_rec()
        super().closeEvent(e)
