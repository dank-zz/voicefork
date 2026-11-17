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


def test_compressor_tames_loud_leaves_quiet():
    loud = tone(200, 1.0, amp=0.5)          # ~-9 dB RMS, above the threshold
    y = render_fx(fx.Compressor(SR, threshold_db=-24, ratio=4, attack_ms=2, release_ms=50), loud)
    in_rms = np.sqrt(np.mean(loud[SR // 2:] ** 2))
    out_rms = np.sqrt(np.mean(y[SR // 2:] ** 2))
    assert np.all(np.isfinite(y))
    assert out_rms < in_rms * 0.8          # clearly turned down

    quiet = tone(200, 1.0, amp=0.01)        # ~-43 dB RMS, below the threshold
    yq = render_fx(fx.Compressor(SR, threshold_db=-24, ratio=4), quiet)
    q_in = np.sqrt(np.mean(quiet[SR // 2:] ** 2))
    q_out = np.sqrt(np.mean(yq[SR // 2:] ** 2))
    assert abs(q_out - q_in) < q_in * 0.1  # left essentially alone


def test_fried_zero_is_passthrough():
    x = tone(200, 0.3)
    assert np.array_equal(fx.Fried(SR, 0.0).process(x), x)


@pytest.mark.parametrize("amount", [0.25, 0.5, 1.0])
def test_fried_is_finite_bounded_and_changes_signal(amount):
    rng = np.random.default_rng(0)
    x = tone(180, 1.0) + 0.05 * rng.standard_normal(SR).astype(np.float32)
    y = render_fx(fx.Fried(SR, amount), x)
    assert np.all(np.isfinite(y))
    assert np.max(np.abs(y)) <= 1.0
    assert len(y) == len(x)
    assert np.sqrt(np.mean((y - x) ** 2)) > 1e-3     # it did something


def test_fried_fits_realtime_budget():
    chain = build_chain("clean", SR, fried=1.0)
    block = tone(200, 256 / SR)
    for _ in range(20):
        chain.process(block)
    t0 = time.perf_counter()
    reps = 200
    for _ in range(reps):
        chain.process(block)
    per_block = (time.perf_counter() - t0) / reps
    assert per_block < 0.25 * 256 / SR, f"fried: {per_block * 1e3:.2f} ms per block"


def test_build_chain_with_fried_is_stable():
    rng = np.random.default_rng(1)
    x = tone(180, 1.0) + 0.05 * rng.standard_normal(SR).astype(np.float32)
    chain = build_chain("clean", SR, gate_db=-120, fried=0.8)
    y = np.concatenate([chain.process(x[i:i + 256]) for i in range(0, len(x), 256)])
    assert np.all(np.isfinite(y))
    assert np.max(np.abs(y)) <= 1.0
    assert np.sqrt(np.mean(y[SR // 2:] ** 2)) > 0.01   # not silent


def render_fx(effect, x, block=256):
    return np.concatenate([effect.process(x[i:i + block]) for i in range(0, len(x), block)])
