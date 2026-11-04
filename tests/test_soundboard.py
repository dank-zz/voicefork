"""Soundboard mixer and clip library (no audio devices needed)."""
import numpy as np
import pytest
from scipy.io import wavfile

from voicefork import soundboard as sb


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEFORK_HOME", str(tmp_path / "vc"))


def test_mixer_plays_toggles_and_ends():
    m = sb.Mixer(48000)
    clip = np.ones(1000, np.float32) * 0.5
    assert m.mix(256) is None
    m.toggle("a", clip)
    out = m.mix(256)
    assert np.allclose(out, 0.5) and m.playing == {"a"}
    m.toggle("a", clip)                    # pressing again stops it
    assert m.mix(256) is None and m.playing == frozenset()
    m.toggle("a", clip)
    for _ in range(4):                     # 1000 samples = 4 blocks of 256 (last partial)
        out = m.mix(256)
    assert np.allclose(out[:1000 - 768], 0.5) and np.allclose(out[1000 - 768:], 0)
    assert m.mix(256) is None              # finished


def test_mixer_overlaps_and_stop_all():
    m = sb.Mixer(48000)
    m.volume = 0.5
    m.toggle("a", np.full(512, 0.4, np.float32))
    m.toggle("b", np.full(512, 0.2, np.float32))
    assert np.allclose(m.mix(128), 0.3)
    m.stop_all()
    assert m.mix(128) is None


def test_import_wav_converts_and_normalises(tmp_path):
    src = tmp_path / "Air Horn.wav"
    stereo = np.stack([np.sin(np.arange(44100) / 9), np.sin(np.arange(44100) / 9)], 1) * 0.2
    wavfile.write(src, 44100, (stereo * 32767).astype(np.int16))
    clip = sb.import_file(src)
    assert clip.name == "Air Horn" and abs(clip.seconds - 1.0) < 0.01
    sr, data = wavfile.read(clip.path)
    assert sr == sb.CLIP_SR and data.ndim == 1 and abs(np.max(np.abs(data)) - 0.7) < 0.01
    assert sb.import_file(src).name == "Air Horn 2"     # no overwrite
    assert [c.name for c in sb.list_clips()] == ["Air Horn", "Air Horn 2"]


def test_recording_trims_silence_and_rejects_empty():
    sr = 48000
    x = np.concatenate([np.zeros(sr), 0.5 * np.sin(np.arange(sr // 2) / 5), np.zeros(sr)]).astype(np.float32)
    clip = sb.save_recording(x, sr, "hi")
    assert clip.seconds < 0.75
    with pytest.raises(ValueError):
        sb.save_recording(np.zeros(sr, np.float32), sr)


def test_cache_resamples_to_output_rate():
    clip = sb._save(np.full(48000, 0.1, np.float32), 48000, "beep")
    assert len(sb.ClipCache().get(clip, 40000)) == 40000


def test_mixer_play_restarts_instead_of_stopping():
    m = sb.Mixer(48000)
    clip = np.ones(1000, np.float32)
    m.play("tts", clip)
    m.mix(256)
    m.play("tts", clip)                    # a second message restarts, never cancels
    assert m.mix(256) is not None and m.playing == {"tts"}
