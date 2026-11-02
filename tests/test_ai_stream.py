"""Streaming-engine tests for the AI path. Skipped unless torch + sounddevice are installed.
They use a stand-in voice, so no GPU or model files are needed."""
import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchaudio")
pytest.importorskip("sounddevice")

from voicefork.ai.engine import AIVoiceEngine, StreamSettings  # noqa: E402

SR = 40000


class FakeVoice:
    """Returns the newest input audio (16 kHz -> model rate) like an identity 'voice'."""
    name = "fake"
    last_timings = (0, 0, 0, 0)

    def __init__(self):
        self.device = torch.device("cpu")
        self.tgt_sr = SR
        self.calls = 0

    def reset_state(self):
        pass

    def infer(self, wav16k, block_16k, skip_head, return_length):
        self.calls += 1
        n_out = return_length * (SR // 100)
        n_in = n_out * 16000 // SR
        seg = wav16k[-n_in:]
        return torch.nn.functional.interpolate(seg[None, None], size=n_out, mode="linear")[0, 0]


def run(engine, signal, block):
    out = np.zeros((block, 1), np.float32)
    chunks = []
    for i in range(0, len(signal) - block + 1, block):
        engine._process(signal[i:i + block], out)
        chunks.append(out[:, 0].copy())
    return np.concatenate(chunks)


@pytest.mark.parametrize("bypass", [True, False])
def test_stream_output_is_continuous(bypass):
    eng = AIVoiceEngine(FakeVoice(), 0, 1, StreamSettings(gate_db=-120, context_time=0.5))
    eng.bypass = bypass
    t = np.arange(SR * 3) / SR
    x = (0.3 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    y = run(eng, x, eng.block_frame)
    steady = y[SR:]
    assert np.all(np.isfinite(steady))
    # a 180 Hz sine at 0.3 changes by at most ~0.0085 per sample; a splice click would be far larger
    assert np.max(np.abs(np.diff(steady))) < 0.03
    assert 0.15 < np.max(np.abs(steady)) <= 0.35


def test_block_sizes_line_up():
    eng = AIVoiceEngine(FakeVoice(), 0, 1, StreamSettings(block_time=0.12))
    assert eng.block_frame == int(0.12 * SR)
    assert eng.block_frame_16k == int(0.12 * 16000)
    assert eng.return_length * eng.zc >= eng.block_frame + eng.sola_buffer_frame
