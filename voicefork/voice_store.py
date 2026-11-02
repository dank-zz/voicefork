"""'Get voices' window: starter voices, Hugging Face search, install from file."""
from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:  # noqa: BLE001 - shown to the user
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for c in range(1, len(headers)):
        t.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
    return t


class VoiceStore(QDialog):
    changed = Signal()  # a voice was installed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Get voices")
        self.resize(760, 560)
        self.worker: Worker | None = None
        self.hits = []
        self.files = []
        self.previewer = None

        lay = QVBoxLayout(self)
        lay.addLayout(self._preview_bar())
        tabs = QTabWidget()
        tabs.addTab(self._starter_tab(), "Free starter voices")
        tabs.addTab(self._search_tab(), "Search Hugging Face")
        tabs.addTab(self._file_tab(), "From file")
        lay.addWidget(tabs, 1)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.hide()
        lay.addWidget(self.busy)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self._fill_starter()

    # ---------------------------------------------------------------- tabs
    def _starter_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Speakers from the VCTK research corpus (recorded with consent, Apache-2.0). "
                           "The blends don't sound like any single person."))
        self.starter = _table(["Voice", "Status"])
        v.addWidget(self.starter, 1)
        row = QHBoxLayout()
        pv = QPushButton("Preview")
        pv.setToolTip("Hear your recording through this voice (downloads only the ~55 MB model)")
        pv.clicked.connect(self._preview_starter)
        row.addWidget(pv)
        get = QPushButton("Download selected")
        get.clicked.connect(self._get_starter)
        allb = QPushButton("Download all missing")
        allb.clicked.connect(lambda: self._get_starter(all_missing=True))
        listen = QPushButton("Listen to samples (web)")
        listen.clicked.connect(lambda: self._open("https://huggingface.co/Nekochu/RVC-VCTK_Voice-sample/tree/main"))
        row.addWidget(get)
        row.addWidget(allb)
        row.addStretch(1)
        row.addWidget(listen)
        v.addLayout(row)
        self.starter.doubleClicked.connect(lambda _: self._get_starter())
        return w

    def _search_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        warn = QLabel("Community models are made by anyone and many copy real people's voices. Check the "
                      "model page and license, and never use someone's voice to pass as them.")
        warn.setWordWrap(True)
        v.addWidget(warn)
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search RVC voices, e.g. 'female', 'narrator', 'anime' (empty = most popular)")
        self.query.returnPressed.connect(self._search)
        go = QPushButton("Search")
        go.clicked.connect(self._search)
        row.addWidget(self.query, 1)
        row.addWidget(go)
        v.addLayout(row)

        self.results = _table(["Repository", "License", "Downloads", "Updated"])
        self.results.itemSelectionChanged.connect(self._inspect)
        v.addWidget(self.results, 3)

        v.addWidget(QLabel("Voices in the selected repository:"))
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self._file_picked)
        v.addWidget(self.file_list, 2)

        row = QHBoxLayout()
        row.addWidget(QLabel("Install as"))
        self.name = QLineEdit()
        row.addWidget(self.name, 1)
        self.with_index = QCheckBox("include .index")
        self.with_index.setChecked(True)
        self.with_index.setToolTip("Needed for the Similarity slider. Can be large.")
        row.addWidget(self.with_index)
        page = QPushButton("Open page")
        page.clicked.connect(self._open_repo)
        pv = QPushButton("Preview")
        pv.clicked.connect(self._preview_repo)
        row.addWidget(pv)
        dl = QPushButton("Download")
        dl.clicked.connect(self._download_repo_voice)
        row.addWidget(page)
        row.addWidget(dl)
        v.addLayout(row)
        return w

    def _file_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Install a voice you already have: an RVC .pth file (an .index next to it is "
                           "picked up automatically) or a .zip that contains them, e.g. from your own training."))
        b = QPushButton("Choose .pth or .zip …")
        b.clicked.connect(self._from_file)
        v.addWidget(b)
        v.addStretch(1)
        return w

    def _preview_bar(self):
        from .ai import preview
        row = QHBoxLayout()
        self.rec_btn = QPushButton(f"Record my voice ({preview.DEMO_SECONDS} s)")
        self.rec_btn.clicked.connect(self._record)
        self.play_rec = QPushButton("Play recording")
        self.play_rec.clicked.connect(self._play_recording)
        self.pv_pitch = QSpinBox()
        self.pv_pitch.setRange(-24, 24)
        self.pv_pitch.setSuffix(" st")
        main = self.parent()
        self.pv_pitch.setValue(main.pitch.value() if main is not None and hasattr(main, "pitch") else 0)
        self.pv_pitch.setToolTip("Pitch for previews: about +12 for male → female, -12 for female → male")
        self.rec_state = QLabel("")
        self.rec_state.setObjectName("muted")
        stop = QPushButton("Stop")
        stop.setToolTip("Stop playback")
        stop.clicked.connect(self._stop_audio)
        row.addWidget(self.rec_btn)
        row.addWidget(self.play_rec)
        row.addWidget(QLabel("Preview pitch"))
        row.addWidget(self.pv_pitch)
        row.addWidget(stop)
        row.addWidget(self.rec_state, 1)
        self.rec_state.setText("recording saved" if preview.demo_path().is_file()
                               else "record a few sentences first, then preview voices")
        return row

    # ---------------------------------------------------------------- preview
    def _devices(self):
        main = self.parent()
        mic = main.mic.currentData() if main is not None and hasattr(main, "mic") else None
        out = main.phones.currentData() if main is not None and hasattr(main, "phones") else None
        return mic, out

    def _record(self):
        from .ai import preview
        mic, _ = self._devices()
        self.rec_state.setText("Recording… talk now!")
        self._run("Recording …", lambda: preview.record_demo(mic),
                  lambda _: (self.rec_state.setText("recording saved"), self.status.setText("Recorded.")))

    def _play(self, y, sr):
        from .ai import preview
        _, out = self._devices()
        try:
            preview.play(y, sr, out)
        except Exception as e:  # noqa: BLE001
            self._failed(f"Could not play audio: {e}")

    def _stop_audio(self):
        import sounddevice as sd
        sd.stop()

    def _play_recording(self):
        from .ai import preview
        clip = preview.load_demo()
        if clip is None:
            self.status.setText("Record your voice first.")
            return
        self._play(clip, preview.DEMO_SR)

    def _start_preview(self, title, fetch):
        from .ai import preview
        clip = preview.load_demo()
        if clip is None:
            self.status.setText("Record your voice first (button at the top).")
            return
        if self.previewer is None:
            self.previewer = preview.get_previewer()
        pitch, pv = self.pv_pitch.value(), self.previewer

        def work():
            return pv.convert(fetch(), clip, pitch)

        self._run(f"Preparing preview of {title} (first time loads the AI models) …", work,
                  lambda r: (self._play(*r), self.status.setText(f"Playing preview: {title}")))

    def _preview_starter(self):
        from .ai import assets, preview
        row = self.starter.currentRow()
        if row < 0:
            self.status.setText("Select a voice first.")
            return
        key = self.starter.item(row, 0).data(Qt.UserRole)
        name = self.starter.item(row, 0).text()

        def fetch():
            pth = next(f for f in assets.starter_files(key, with_index=False) if f.endswith(".pth"))
            return preview.fetch_pth(assets.STARTER_REPO, pth)

        self._start_preview(name, fetch)

    def _preview_repo(self):
        from .ai import preview
        hit, row = self._current_hit(), self.file_list.currentRow()
        if not hit or not (0 <= row < len(self.files)):
            self.status.setText("Select a repository and a voice file first.")
            return
        vf = self.files[row]
        self._start_preview(vf.path, lambda: preview.fetch_pth(hit.repo_id, vf.path))

    # ---------------------------------------------------------------- worker plumbing
    def _run(self, text, fn, on_done):
        if self.worker and self.worker.isRunning():
            self.status.setText("Busy - wait for the current task to finish.")
            return
        self.status.setText(text)
        self.busy.show()
        self.worker = Worker(fn, self)
        self.worker.done.connect(lambda r: (self.busy.hide(), on_done(r)))
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _failed(self, msg):
        self.busy.hide()
        if "No module named 'huggingface_hub'" in msg:
            msg += "\n\nInstall it: .venv\\Scripts\\python -m pip install huggingface_hub"
        self.status.setText("Failed.")
        QMessageBox.warning(self, "Get voices", msg)

    def _installed(self, dest):
        self.status.setText(f"Installed: {Path(dest).name}")
        self._fill_starter()
        self.changed.emit()

    def _open(self, url):
        QDesktopServices.openUrl(QUrl(url))

    # ---------------------------------------------------------------- starter
    def _fill_starter(self):
        from .ai import assets
        self.starter.setRowCount(0)
        for key, (_, name, _) in assets.STARTER.items():
            r = self.starter.rowCount()
            self.starter.insertRow(r)
            it = QTableWidgetItem(name)
            it.setData(Qt.UserRole, key)
            self.starter.setItem(r, 0, it)
            self.starter.setItem(r, 1, QTableWidgetItem("installed" if assets.starter_installed(key) else ""))

    def _get_starter(self, all_missing=False):
        from .ai import assets
        if all_missing:
            keys = [k for k in assets.STARTER if not assets.starter_installed(k)]
        else:
            row = self.starter.currentRow()
            keys = [self.starter.item(row, 0).data(Qt.UserRole)] if row >= 0 else []
        keys = [k for k in keys if not assets.starter_installed(k)]
        if not keys:
            self.status.setText("Nothing to download (select a voice that isn't installed).")
            return

        def work():
            for k in keys:
                assets.get_starter_voice(k)
            return f"{len(keys)} voice(s)"

        self._run(f"Downloading {len(keys)} voice(s) (~200 MB each) …", work, self._installed)

    # ---------------------------------------------------------------- search
    def _search(self):
        from .ai import catalog
        q = self.query.text()
        self._run("Searching Hugging Face …", lambda: catalog.search(q), self._show_hits)

    def _show_hits(self, hits):
        self.hits = hits
        self.results.setRowCount(0)
        self.file_list.clear()
        for h in hits:
            r = self.results.rowCount()
            self.results.insertRow(r)
            for c, val in enumerate((h.repo_id, h.license, f"{h.downloads:,}", h.updated)):
                self.results.setItem(r, c, QTableWidgetItem(val))
        self.status.setText(f"{len(hits)} repositories. Select one to see its voices.")

    def _current_hit(self):
        r = self.results.currentRow()
        return self.hits[r] if 0 <= r < len(self.hits) else None

    def _inspect(self):
        from .ai import catalog
        hit = self._current_hit()
        if not hit or (self.worker and self.worker.isRunning()):
            return
        self.file_list.clear()
        self._run(f"Looking inside {hit.repo_id} …", lambda: catalog.repo_voices(hit.repo_id), self._show_files)

    def _show_files(self, files):
        self.files = files
        self.file_list.clear()
        for f in files:
            self.file_list.addItem(QListWidgetItem(f.label))
        if files:
            self.file_list.setCurrentRow(0)
            self.status.setText(f"{len(files)} voice file(s). Pick one and press Download.")
        else:
            self.status.setText("No RVC voice files (.pth or .zip) in this repository.")

    def _file_picked(self, row):
        if 0 <= row < len(self.files):
            self.name.setText(self.files[row].default_name)

    def _open_repo(self):
        hit = self._current_hit()
        if hit:
            self._open(hit.url)

    def _download_repo_voice(self):
        from .ai import catalog
        hit, row = self._current_hit(), self.file_list.currentRow()
        if not hit or not (0 <= row < len(self.files)):
            self.status.setText("Select a repository and a voice file first.")
            return
        vf, name, idx = self.files[row], self.name.text().strip(), self.with_index.isChecked()
        if not name:
            self.status.setText("Give the voice a name.")
            return
        self._run(f"Downloading {vf.path} …",
                  lambda: catalog.install_from_repo(hit.repo_id, vf, name, idx), self._installed)

    # ---------------------------------------------------------------- local file
    def _from_file(self):
        from .ai import catalog
        path, _ = QFileDialog.getOpenFileName(self, "Choose a voice", str(Path.home() / "Downloads"),
                                              "RVC voice (*.pth *.zip)")
        if not path:
            return
        p = Path(path)
        name, ok = QInputDialog.getText(self, "Install voice", "Name:", text=catalog.safe_name(p.stem))
        if ok and name.strip():
            self._run(f"Installing {p.name} …", lambda: catalog.install_from_file(p, name.strip()), self._installed)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.status.setText("Still working - it will finish in the background.")
        super().closeEvent(e)
