"""Preview helpers without network/GPU (Hugging Face and the sound card are stubbed)."""
import sys
import types
import zipfile

import numpy as np
import pytest

from voicefork.ai import preview


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEFORK_HOME", str(tmp_path / "vc"))


def test_fetch_pth_from_zip_takes_the_voice_not_checkpoints(tmp_path, monkeypatch):
    z = tmp_path / "bundle.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("x/Nova.pth", b"v" * 100)
        f.writestr("x/G_9000.pth", b"c" * 1000)
    hub = types.ModuleType("huggingface_hub")
    hub.hf_hub_download = lambda repo, path: str(z)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    out = preview.fetch_pth("someone/repo", "bundle.zip")
    assert out.read_bytes() == b"v" * 100


def test_record_and_reload_demo(monkeypatch):
    sd = types.ModuleType("sounddevice")
    sd.rec = lambda n, **k: (0.3 * np.sin(np.arange(n) / 20))[:, None].astype(np.float32)
    sd.wait = lambda: None
    sd.query_devices = lambda dev=None, kind=None: {"default_samplerate": 44100.0}
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    x = preview.record_demo(None, seconds=1)
    assert abs(np.max(np.abs(x)) - 0.9) < 1e-3  # normalised
    y = preview.load_demo()
    assert len(y) == preview.DEMO_SR and np.allclose(x, y, atol=1e-6)  # 44.1k mic -> 48k file


def test_play_resamples_to_device_rate(monkeypatch):
    played = {}
    sd = types.ModuleType("sounddevice")
    sd.query_devices = lambda dev=None, kind=None: {"default_samplerate": 44100.0}
    sd.stop = lambda: None
    sd.play = lambda y, rate, device=None: played.update(n=len(y), rate=rate)
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    preview.play(np.zeros(48000, np.float32), 48000, None)
    assert played == {"n": 44100, "rate": 44100}
