"""Soundboard: a clip library on disk and a real-time mixer.

Clips live in <home>/sounds as 48 kHz mono WAV (anything you import is
converted once, so playback never decodes). The Mixer is fed from the UI
thread through a queue and mixed inside the audio callback, so starting a
clip never blocks or glitches the voice.
"""
from __future__ import annotations

import queue
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ai import assets

CLIP_SR = 48000
MAX_SECONDS = 60
AUDIO_TYPES = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus")


def sounds_dir() -> Path:
    d = assets.home() / "sounds"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Clip:
    name: str
    path: Path
    seconds: float


def list_clips() -> list[Clip]:
    from scipy.io import wavfile
    out = []
    for p in sorted(sounds_dir().glob("*.wav"), key=lambda q: q.stem.lower()):
        try:
            sr, data = wavfile.read(p, mmap=True)
            out.append(Clip(p.stem, p, len(data) / sr))
        except Exception:  # noqa: BLE001 - skip unreadable files
            continue
    return out


def _safe_stem(name: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")[:40] or "clip"
    base, n = stem, 2
    while (sounds_dir() / f"{stem}.wav").exists():
        stem = f"{base} {n}"
        n += 1
    return stem


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x.astype(np.float32)
    from scipy.signal import resample_poly
    g = np.gcd(int(src), int(dst))
    return resample_poly(x, dst // g, src // g).astype(np.float32)


def _save(x: np.ndarray, sr: int, name: str) -> Clip:
    from scipy.io import wavfile
    x = _resample(x, sr, CLIP_SR)[: MAX_SECONDS * CLIP_SR]
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0:
        x = x * (0.7 / peak)  # even loudness across clips, with headroom for the voice
    path = sounds_dir() / f"{_safe_stem(name)}.wav"
    wavfile.write(path, CLIP_SR, x.astype(np.float32))
    return Clip(path.stem, path, len(x) / CLIP_SR)


def import_file(src: Path) -> Clip:
    """Decode any common audio file, convert to the library format."""
    if src.suffix.lower() not in AUDIO_TYPES:
        raise ValueError(f"{src.name}: not an audio file ({', '.join(AUDIO_TYPES)})")
    try:
        import soundfile as sf
        data, sr = sf.read(str(src), dtype="float32", always_2d=True)
    except ImportError:
        if src.suffix.lower() != ".wav":
            raise RuntimeError("MP3/OGG/FLAC need the soundfile package:  .venv\\Scripts\\python -m pip install soundfile")
        from scipy.io import wavfile
        sr, data = wavfile.read(src)
        if data.dtype.kind in "iu":
            data = data.astype(np.float32) / np.iinfo(data.dtype).max
    mono = data.mean(axis=1) if data.ndim == 2 else data
    if len(mono) == 0:
        raise ValueError(f"{src.name} is empty")
    return _save(mono, int(sr), src.stem)


def save_recording(x: np.ndarray, sr: int, name: str = "recording") -> Clip:
    # trim silence at both ends so the clip starts the moment you press it
    loud = np.flatnonzero(np.abs(x) > 0.02) if len(x) else np.zeros(0, int)
    x = x[max(0, loud[0] - sr // 50): loud[-1] + sr // 10] if len(loud) else x[:0]
    if len(x) < sr // 10:
        raise ValueError("The recording was silent or too short.")
    return _save(x, sr, name)


def rename_clip(clip: Clip, new: str) -> Clip:
    stem = _safe_stem(new)
    path = clip.path.with_name(f"{stem}.wav")
    shutil.move(clip.path, path)
    return Clip(stem, path, clip.seconds)


def delete_clip(clip: Clip) -> None:
    clip.path.unlink(missing_ok=True)


class ClipCache:
    """Clips resampled to a given output rate, loaded once."""

    def __init__(self):
        self._c: dict[tuple, np.ndarray] = {}

    def get(self, clip: Clip, sr: int) -> np.ndarray:
        from scipy.io import wavfile
        key = (str(clip.path), clip.path.stat().st_mtime_ns, sr)
        if key not in self._c:
            file_sr, data = wavfile.read(clip.path)
            self._c[key] = _resample(np.asarray(data, np.float32), file_sr, sr)
        return self._c[key]


class Mixer:
    """Mixes playing clips into an audio stream. toggle()/stop_all() from any thread,
    mix() from the audio thread only."""

    def __init__(self, sr: int):
        self.sr = sr
        self.volume = 1.0
        self._in: queue.SimpleQueue = queue.SimpleQueue()
        self._active: list[list] = []          # [clip name, samples, position]
        self.playing: frozenset[str] = frozenset()

    def toggle(self, name: str, samples: np.ndarray):
        self._in.put(("toggle", name, samples))

    def play(self, name: str, samples: np.ndarray):
        """Start (or restart) a sound; unlike toggle, never stops it."""
        self._in.put(("play", name, samples))

    def stop_all(self):
        self._in.put(("stop",))

    def mix(self, n: int) -> np.ndarray | None:
        while True:
            try:
                msg = self._in.get_nowait()
            except queue.Empty:
                break
            if msg[0] == "stop":
                self._active = []
            elif msg[0] == "play":
                self._active = [a for a in self._active if a[0] != msg[1]] + [[msg[1], msg[2], 0]]
            elif any(a[0] == msg[1] for a in self._active):
                self._active = [a for a in self._active if a[0] != msg[1]]   # pressing again stops it
            else:
                self._active.append([msg[1], msg[2], 0])
        if not self._active:
            if self.playing:
                self.playing = frozenset()
            return None
        out = np.zeros(n, np.float32)
        keep = []
        for a in self._active:
            chunk = a[1][a[2]:a[2] + n]
            out[:len(chunk)] += chunk
            a[2] += n
            if a[2] < len(a[1]):
                keep.append(a)
        self._active = keep
        self.playing = frozenset(a[0] for a in keep)
        return out * self.volume


class LocalPlayer:
    """Plays clips on your own headphones when the live monitor isn't already doing it."""

    def __init__(self, device: int | None):
        import sounddevice as sd

        from .devices import wasapi_settings
        info = sd.query_devices(device, "output")
        self.sr = int(info["default_samplerate"])
        self.mixer = Mixer(self.sr)
        dev = device if device is not None else sd.default.device[1]
        self.stream = sd.OutputStream(
            device=device, samplerate=self.sr, channels=min(2, info["max_output_channels"]),
            dtype="float32", blocksize=0, callback=self._cb,
            extra_settings=wasapi_settings(dev) if dev is not None and dev >= 0 else None)
        self.stream.start()

    def _cb(self, outdata, frames, _t, _s):
        y = self.mixer.mix(frames)
        outdata[:] = 0 if y is None else np.clip(y, -1, 1)[:, None]

    def close(self):
        self.stream.abort()
        self.stream.close()
