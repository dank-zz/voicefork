"""'Hear myself': plays the processed voice on a second device (your headphones).

The engine's audio callback pushes each finished block into a small deque;
this stream's own callback pops them. deque append/popleft are atomic, so no
locks touch either audio thread. The queue is capped so the monitor can never
drift more than a few blocks behind.
"""
from __future__ import annotations

from collections import deque

import numpy as np
import sounddevice as sd

from .devices import wasapi_settings


class Monitor:
    def __init__(self, device: int, samplerate: int, blocksize: int, volume: float = 1.0):
        self.device, self.sr, self.blocksize = device, samplerate, blocksize
        self.volume = volume
        self._q: deque = deque(maxlen=3)
        self._pending = np.zeros(0, np.float32)
        ch = min(2, sd.query_devices(device)["max_output_channels"])
        self.stream = sd.OutputStream(
            device=device, samplerate=samplerate, blocksize=blocksize, channels=ch,
            dtype="float32", latency="low", callback=self._callback,
            extra_settings=wasapi_settings(device),
        )

    def push(self, block: np.ndarray) -> None:
        """Called from the engine's audio thread."""
        self._q.append(block.copy())

    def _callback(self, outdata, frames, _t, _status):
        buf = self._pending
        while len(buf) < frames:
            try:
                buf = np.concatenate((buf, self._q.popleft()))
            except IndexError:  # underrun: play what we have, then silence
                buf = np.concatenate((buf, np.zeros(frames - len(buf), np.float32)))
        self._pending = buf[frames:]
        outdata[:] = (buf[:frames] * self.volume)[:, None]

    def start(self) -> "Monitor":
        self.stream.start()
        return self

    def stop(self) -> None:
        self.stream.abort()
        self.stream.close()
