"""Train your own RVC voice: recordings -> model in the voices folder.

Runs RVC's own training scripts (vendored in ai/trainer) as child processes,
in the same order as the RVC WebUI:

  1. preprocess   slice recordings into ~3.7 s pieces, resample
  2. pitch        RMVPE pitch curves
  3. features     HuBERT speech features
  4. train        fine-tune the pretrained v2 40k model
  5. index        retrieval index (the Similarity slider)

Separate processes keep the app responsive, release all GPU memory when done,
and let Cancel stop everything cleanly.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from random import shuffle

from . import assets

TRAINER = Path(__file__).resolve().parent / "trainer"
HF_REPO = "lj1995/VoiceConversionWebUI"
PRETRAINED = ("pretrained_v2/f0G40k.pth", "pretrained_v2/f0D40k.pth")
SR_TAG, SR = "40k", 40000
MIN_SECONDS, GOOD_SECONDS = 120, 600

PRESETS = {  # name: (epochs, rough minutes on a mid-range RTX GPU with ~10 min of audio)
    "Quick": (80, 15),
    "Standard": (200, 45),
    "Best": (400, 120),
}
STAGES = (  # name, share of the progress bar
    ("Downloading base models", 0.04), ("Preparing audio", 0.04), ("Pitch", 0.06),
    ("Speech features", 0.06), ("Training", 0.76), ("Index", 0.04),
)


# Harvard sentences (IEEE, 1969; public domain): short, varied, cover English sounds well.
SENTENCES = [
    "The birch canoe slid on the smooth planks.", "Glue the sheet to the dark blue background.",
    "It's easy to tell the depth of a well.", "These days a chicken leg is a rare dish.",
    "Rice is often served in round bowls.", "The juice of lemons makes fine punch.",
    "The box was thrown beside the parked truck.", "Four hours of steady work faced us.",
    "A large size in stockings is hard to sell.", "The boy was there when the sun rose.",
    "A rod is used to catch pink salmon.", "The source of the huge river is the clear spring.",
    "Kick the ball straight and follow through.", "Help the woman get back to her feet.",
    "A pot of tea helps to pass the evening.", "Smoky fires lack flame and heat.",
    "The soft cushion broke the man's fall.", "The salt breeze came across from the sea.",
    "The girl at the booth sold fifty bonds.", "The small pup gnawed a hole in the sock.",
    "The fish twisted and turned on the bent hook.", "Press the pants and sew a button on the vest.",
    "The swan dive was far short of perfect.", "The beauty of the view stunned the young boy.",
    "Two blue fish swam in the tank.", "Her purse was full of useless trash.",
    "The colt reared and threw the tall rider.", "It snowed, rained, and hailed the same morning.",
    "Read verse out loud for pleasure.", "Hoist the load to your left shoulder.",
    "Take the winding path to reach the lake.", "Note closely the size of the gas tank.",
    "Wipe the grease off his dirty face.", "Mend the coat before you go out.",
    "The wrist was badly strained and hung limp.", "The stray cat gave birth to kittens.",
    "The young girl gave no clear response.", "The meal was cooked before the bell rang.",
    "What joy there is in living.", "A king ruled the state in the early days.",
    "The ship was torn apart on the sharp reef.", "Sickness kept him home the third week.",
    "The wide road shimmered in the hot sun.", "The lazy cow lay in the cool grass.",
    "Lift the square stone over the fence.", "The rope will bind the seven books at once.",
    "Hop over the fence and plunge in.", "The friendly gang left the drug store.",
    "Mesh wire keeps chicks inside.", "The frosty air passed through the coat.",
    "The crooked maze failed to fool the mouse.", "Adding fast leads to wrong sums.",
    "The show was a flop from the very start.", "A saw is a tool used for making boards.",
    "The wagon moved on well oiled wheels.", "March the soldiers past the next hill.",
    "A cup of sugar makes sweet fudge.", "Place a rosebush near the porch steps.",
    "Both lost their lives in the raging storm.",
]
FREE_TALK = [
    "Talk freely for half a minute: describe the room you're in.",
    "Talk freely: what did you do yesterday? Use your normal voice.",
    "Ask a few questions out loud, like you would in a game chat.",
    "Say something excited, then something calm.",
    "Talk freely: explain how to make your favourite food.",
    "Count from one to twenty, then laugh a little.",
]


def prompts():
    out, free = [], iter(FREE_TALK * 3)
    for i, s in enumerate(SENTENCES):
        out.append(s)
        if i % 8 == 7:
            out.append(next(free))
    return out


def workspace() -> Path:
    d = assets.home() / "training"
    d.mkdir(parents=True, exist_ok=True)
    return d


def recordings_dir(voice: str) -> Path:
    from .catalog import safe_name
    d = assets.home() / "recordings" / safe_name(voice)
    d.mkdir(parents=True, exist_ok=True)
    return d


def dataset_seconds(folder: Path) -> float:
    import soundfile as sf
    total = 0.0
    for f in folder.glob("*.wav"):
        try:
            total += sf.info(str(f)).duration
        except Exception:  # noqa: BLE001
            pass
    return total


class Cancelled(Exception):
    pass


@dataclass
class Progress:
    stage: str
    fraction: float          # whole job, 0..1
    detail: str = ""
    eta_s: float | None = None


def _batch_size() -> int:
    import torch
    gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    return 4 if gb < 6 else 8 if gb < 11 else 12


class TrainJob:
    """Blocking; run it from a worker thread. report(Progress) is called often, cancel() from any thread."""

    def __init__(self, voice_name: str, preset: str, report=lambda p: None, log=lambda line: None):
        from .catalog import safe_name
        self.voice = safe_name(voice_name)
        self.epochs = PRESETS[preset][0]
        self.report, self.log = report, log
        self.exp = "vf_" + re.sub(r"[^A-Za-z0-9]+", "_", self.voice).strip("_")[:30] + time.strftime("_%Y%m%d%H%M%S")
        self.ws = workspace()
        self.exp_dir = self.ws / "logs" / self.exp
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    # ------------------------------------------------------------- control
    def cancel(self):
        self._cancelled = True
        p = self._proc
        if p is not None and p.poll() is None:
            if sys.platform == "win32":  # training spawns child processes: kill the whole tree
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
            else:
                p.kill()

    def _check(self):
        if self._cancelled:
            raise Cancelled()

    def _stage(self, index: int, inner: float = 0.0, detail: str = "", eta=None):
        done = sum(w for _, w in STAGES[:index])
        self.report(Progress(STAGES[index][0], done + STAGES[index][1] * min(1.0, inner), detail, eta))

    # ------------------------------------------------------------- steps
    def _run(self, script: str, *args, on_line=None):
        self._check()
        env = dict(os.environ)
        env.update({
            "PYTHONPATH": str(TRAINER) + os.pathsep + env.get("PYTHONPATH", ""),
            "VF_HUBERT_DIR": str(assets.hubert_dir()),
            "VF_RMVPE": str(assets.rmvpe_path()),
            "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
        })
        cmd = [sys.executable, str(TRAINER / script), *map(str, args)]
        self.log("$ " + " ".join(cmd[1:]))
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._proc = subprocess.Popen(cmd, cwd=self.ws, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                      errors="replace", creationflags=flags)
        tail = []
        for line in self._proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            tail = (tail + [line])[-30:]
            self.log(line)
            if on_line:
                on_line(line)
        code = self._proc.wait()
        self._proc = None
        self._check()
        if code != 0:
            raise RuntimeError(f"{Path(script).name} failed (exit {code}):\n" + "\n".join(tail[-12:]))

    def _setup(self):
        from huggingface_hub import hf_hub_download
        self._stage(0)
        if assets.missing():
            assets.download()
        for i, f in enumerate(PRETRAINED):
            dst = self.ws / "assets" / f
            if not dst.is_file():
                self._stage(0, i / 3, f"downloading {Path(f).name}")
                hf_hub_download(HF_REPO, f, local_dir=self.ws / "assets")
        if not (self.ws / "logs" / "mute" / "0_gt_wavs").is_dir():
            self._stage(0, 2 / 3, "downloading mute.zip")
            z = hf_hub_download(HF_REPO, "mute.zip", local_dir=self.ws / "downloads")
            with zipfile.ZipFile(z) as zf:
                for m in zf.infolist():  # stay inside logs/ whatever the archive says
                    target = (self.ws / "logs" / m.filename).resolve()
                    if str(target).startswith(str((self.ws / "logs").resolve())) and not m.is_dir():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(zf.read(m))
        (self.ws / "assets" / "weights").mkdir(parents=True, exist_ok=True)

    def _write_filelist_and_config(self):
        gt, feat = self.exp_dir / "0_gt_wavs", self.exp_dir / "3_feature768"
        f0, f0nsf = self.exp_dir / "2a_f0", self.exp_dir / "2b-f0nsf"
        stem = lambda d: {p.name.split(".")[0] for p in d.iterdir()}  # noqa: E731
        names = stem(gt) & stem(feat) & stem(f0) & stem(f0nsf)
        if not names:
            raise RuntimeError("No usable audio after preparation. Is the recording silent?")
        p = lambda x: str(x).replace("\\", "/")  # noqa: E731
        lines = [f"{p(gt)}/{n}.wav|{p(feat)}/{n}.npy|{p(f0)}/{n}.wav.npy|{p(f0nsf)}/{n}.wav.npy|0" for n in sorted(names)]
        mute = self.ws / "logs" / "mute"
        lines += [f"{p(mute)}/0_gt_wavs/mute{SR_TAG}.wav|{p(mute)}/3_feature768/mute.npy|"
                  f"{p(mute)}/2a_f0/mute.wav.npy|{p(mute)}/2b-f0nsf/mute.wav.npy|0"] * 2
        shuffle(lines)
        (self.exp_dir / "filelist.txt").write_text("\n".join(lines), encoding="utf-8")
        # RVC picks v1/40k.json for v2 40k as well (same network size)
        shutil.copy(TRAINER / "configs" / "v1" / f"{SR_TAG}.json", self.exp_dir / "config.json")
        return len(names)

    def run(self, recordings: Path) -> Path:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("Training a voice needs an NVIDIA GPU.")
        if dataset_seconds(recordings) < MIN_SECONDS:
            raise RuntimeError(f"Record at least {MIN_SECONDS // 60} minutes first (10 is best).")
        is_half = "True" if torch.cuda.get_device_capability(0) >= (7, 0) else "False"
        self.exp_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._setup()

            self._stage(1)
            self._run("train/preprocess.py", recordings, SR, 1, self.exp_dir, "True", 3.7)

            self._stage(2)
            self._run("train/dataset/extract_f0.py", "cuda", 1, 0, 0, self.exp_dir, is_half)

            self._stage(3)
            self._run("train/dataset/extract_hubert_feature.py", "cuda", 1, 0, 0, self.exp_dir, "v2", is_half)

            pieces = self._write_filelist_and_config()
            started, first_epoch_t = time.time(), [None]

            def on_train_line(line):
                m = re.search(r"====>\D*(\d+)", line)
                if not m:
                    return
                epoch = int(m.group(1))
                elapsed = time.time() - started
                per = elapsed / max(1, epoch)
                self._stage(4, epoch / self.epochs, f"epoch {epoch} / {self.epochs}",
                            eta=per * (self.epochs - epoch) + 60)

            self._stage(4, 0, f"{pieces} pieces of audio, {self.epochs} epochs")
            self._run("train/train.py", "-e", self.exp, "-sr", SR_TAG, "-f0", 1, "-bs", _batch_size(),
                      "-g", 0, "-te", self.epochs, "-se", self.epochs,
                      "-pg", f"assets/{PRETRAINED[0]}", "-pd", f"assets/{PRETRAINED[1]}",
                      "-l", 1, "-c", 0, "-sw", 0, "-v", "v2", on_line=on_train_line)

            self._stage(5)
            self._run("train/train_index.py", self.exp, "v2", self.ws / "indexes", max(1, (os.cpu_count() or 2) // 2), "single")
            return self._install()
        finally:
            self._cleanup()

    def _install(self) -> Path:
        weights = self.ws / "assets" / "weights" / f"{self.exp}.pth"
        if not weights.is_file():
            raise RuntimeError("Training finished but no model file was written.")
        dest = assets.voices_dir() / self.voice
        n = 2
        while dest.exists() and any(dest.glob("*.pth")):
            dest = assets.voices_dir() / f"{self.voice} {n}"
            n += 1
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(weights), dest / f"{dest.name}.pth")
        for idx in self.exp_dir.glob("added_*.index"):
            shutil.copy2(idx, dest / idx.name)
        self.report(Progress("Done", 1.0, dest.name))
        return dest

    def _cleanup(self):
        # checkpoints and features are hundreds of MB; the recordings stay so you can retrain
        shutil.rmtree(self.exp_dir, ignore_errors=True)
        for idx in (self.ws / "indexes").glob(f"{self.exp}_*"):
            idx.unlink(missing_ok=True)
