"""Type-to-speak helpers that don't need Windows speech."""
import numpy as np

from voicefork import tts


def test_guess_gender_from_voice_names():
    assert tts.guess_gender("Female - Irish (p340)") == "Female"
    assert tts.guess_gender("Male 2 (p274)") == "Male"
    assert tts.guess_gender("Blend - something") is None


def test_effect_is_applied_offline():
    x = (0.3 * np.sin(np.arange(tts.TTS_SR) / 20)).astype(np.float32)
    y = tts.apply_effect(x, "radio")
    assert y.shape == x.shape and np.all(np.isfinite(y)) and not np.allclose(x, y)
