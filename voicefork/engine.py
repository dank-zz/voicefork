"""Real-time loop: mic -> effect chain -> virtual cable.

The audio callback runs on PortAudio's high-priority thread. It must never
block, so everything it touches is either owned by it (the current chain) or
handed over through a lock-free SimpleQueue (preset changes). Chains are
built on the UI thread, then swapped in with a one-block crossfade so preset
switches don't click.
"""
from __future__ import annotations

import queue
import time

import numpy as np
import sounddevice as sd

from .devices import wasapi_settings
from .presets import build_chain


class VoiceEngine:
    def __init__(self, input_device: int, output_device: int, samplerate: int = 48000,
                 blocksize: int = 256, preset: str = "clean", gate_db: float = -50.0,
                 gain_db: float = 0.0):
        self.input_device, self.output_device = input_device, output_device
        self.sr, self.blocksize = samplerate, blocksize
        self.gate_db, self.gain_db = gate_db, gain_db
        self.preset = preset
        self._chain = build_chain(preset, samplerate, gate_db, gain_db)
        self._pending: queue.SimpleQueue = queue.SimpleQueue()
        self.muted = False
        # read-only stats for the UI
        self.peak_in = 0.0
        self.peak_out = 0.0
        self.xruns = 0
        self.cpu_load = 0.0
        self._fade = np.linspace(0.0, 1.0, blocksize, dtype=np.float32)
        self.stream: sd.Stream | None = None
        self.monitor = None  # optional Monitor: hear yourself in headphones
        self.soundboard = None  # optional soundboard Mixer

    # ---- control (call from any thread) ----------------------------------
    def set_preset(self, name: str) -> None:
        chain = build_chain(name, self.sr, self.gate_db, self.gain_db)  # may raise KeyError
        self.preset = name
        self._pending.put(chain)

    def set_gate(self, gate_db: float) -> None:
        """-120 turns the gate off. Rebuilds the chain (crossfaded in the callback)."""
        self.gate_db = gate_db
        self.set_preset(self.preset)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted

    # ---- audio thread ----------------------------------------------------
    def _callback(self, indata, outdata, frames, _time, status):
        t0 = time.perf_counter()
        if status:
            self.xruns += 1
        x = indata[:, 0].copy()
        self.peak_in = float(np.max(np.abs(x)))

        new = None
        while True:
            try:
                new = self._pending.get_nowait()
            except queue.Empty:
                break
        if new is not None:
            fade = self._fade if frames == len(self._fade) else np.linspace(0, 1, frames, dtype=np.float32)
            y = self._chain.process(x) * (1 - fade) + new.process(x) * fade
            self._chain = new
        else:
            y = self._chain.process(x)

        if self.muted:
            y = np.zeros_like(y)
        sb = self.soundboard
        if sb is not None:
            clips = sb.mix(len(y))
            if clips is not None:
                y = y + clips
        np.clip(y, -1.0, 1.0, out=y)
        self.peak_out = float(np.max(np.abs(y)))
        outdata[:] = y[:, None]
        mon = self.monitor
        if mon is not None:
            mon.push(y)
        self.cpu_load = (time.perf_counter() - t0) / (frames / self.sr)

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        out_ch = min(2, sd.query_devices(self.output_device)["max_output_channels"])
        extra = (wasapi_settings(self.input_device), wasapi_settings(self.output_device))
        if extra == (None, None):
            extra = None
        self.stream = sd.Stream(
            samplerate=self.sr, blocksize=self.blocksize,
            device=(self.input_device, self.output_device),
            channels=(1, out_ch), dtype="float32", latency="low",
            callback=self._callback, extra_settings=extra,
        )
        self.stream.start()

    @property
    def latency_ms(self) -> float:
        if not self.stream:
            return 0.0
        lin, lout = self.stream.latency
        return (lin + lout) * 1000

    def stop(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
