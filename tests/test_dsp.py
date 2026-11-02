"""DSP sanity tests - no audio hardware needed. Run: python -m pytest tests"""
import time

import numpy as np
import pytest

from voicefork import effects as fx
from voicefork.cli import render
from voicefork.presets import PRESETS, build_chain

SR = 48000


def tone(freq, seconds=1.0, amp=0.5):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def peak_freq(x):
    x = x[len(x) // 4:]  # skip warm-up
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spec) * SR / len(x)


@pytest.mark.parametrize("ratio", [0.6, 0.78, 1.25, 1.6])
def test_pitch_shift_hits_target(ratio):
    y = render_fx(fx.PitchShift(SR, ratio), tone(220, 2.0))
    assert abs(peak_freq(y) - 220 * ratio) < 220 * ratio * 0.02


def test_pitch_shift_is_block_size_independent():
    x = tone(300, 0.5)
    a = render_fx(fx.PitchShift(SR, 0.7), x, 64)
    b = render_fx(fx.PitchShift(SR, 0.7), x, 1000)
    assert np.allclose(a, b, atol=1e-4)


@pytest.mark.parametrize("name", list(PRESETS))
def test_presets_are_stable_and_bounded(name):
    rng = np.random.default_rng(0)
    x = tone(180, 2.0) + 0.05 * rng.standard_normal(2 * SR).astype(np.float32)
    y = render(x, SR, name, gate_db=-120)
    assert np.all(np.isfinite(y))
    assert np.max(np.abs(y)) <= 1.0
    assert np.sqrt(np.mean(y[SR:] ** 2)) > 0.01  # not silent


@pytest.mark.parametrize("name", list(PRESETS))
def test_presets_fit_realtime_budget(name):
    """A 256-sample block lasts 5.3 ms; processing must take a small fraction of that."""
    chain = build_chain(name, SR)
    block = tone(200, 256 / SR)
    for _ in range(20):
        chain.process(block)
    t0 = time.perf_counter()
    reps = 200
    for _ in range(reps):
        chain.process(block)
    per_block = (time.perf_counter() - t0) / reps
    assert per_block < 0.25 * 256 / SR, f"{name}: {per_block * 1e3:.2f} ms per block"


def test_noise_gate_silences_quiet_input():
    gate = fx.NoiseGate(SR, threshold_db=-40)
    quiet = render_fx(gate, tone(200, 1.0, amp=0.001))
    assert np.max(np.abs(quiet[SR // 2:])) < 1e-4


def render_fx(effect, x, block=256):
    return np.concatenate([effect.process(x[i:i + block]) for i in range(0, len(x), block)])
