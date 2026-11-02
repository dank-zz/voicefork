"""Type to speak: Windows' built-in voices (SAPI), then your current voice on top.

Text -> SAPI speech at 48 kHz -> (AI voice conversion, or the current effect
preset) -> into the virtual mic like a soundboard clip. The SAPI voice is a
bit robotic, but after AI conversion only its words and rhythm are left:
the timbre is your AI voice's.

Runs in a worker thread (COM is initialised per thread).
"""
from __future__ import annotations

import sys

import numpy as np

TTS_SR = 48000
SAFT48kHz16BitMono = 39   # SAPI audio format id


def available() -> str | None:
    """None if TTS can run here, else why not."""
    if sys.platform != "win32":
        return "Type to speak uses Windows' built-in voices, so it only works on Windows."
    try:
        import comtypes.client  # noqa: F401
    except ImportError:
        return "Type to speak needs comtypes:  .venv\\Scripts\\python -m pip install comtypes"
    return None


def guess_gender(voice_name: str) -> str | None:
    n = voice_name.lower()
    if n.startswith("female") or " female" in n:
        return "Female"
    if n.startswith("male") or " male" in n:
        return "Male"
    return None


def synthesize(text: str, gender: str | None = None, rate: int = 0) -> np.ndarray:
    """Speak `text` with a Windows voice (matching `gender` if one is installed). Returns float32 mono @ 48 kHz."""
    why = available()
    if why:
        raise RuntimeError(why)
    import comtypes
    import comtypes.client as cc

    comtypes.CoInitialize()
    try:
        voice = cc.CreateObject("SAPI.SpVoice")
        if gender:
            tokens = voice.GetVoices(f"Gender={gender}", "")
            if tokens.Count:
                voice.Voice = tokens.Item(0)
        voice.Rate = max(-10, min(10, rate))
        stream = cc.CreateObject("SAPI.SpMemoryStream")
        fmt = cc.CreateObject("SAPI.SpAudioFormat")
        fmt.Type = SAFT48kHz16BitMono
        stream.Format = fmt
        voice.AudioOutputStream = stream
        voice.Speak(text, 0)
        raw = bytes(stream.GetData())
    finally:
        comtypes.CoUninitialize()
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if not len(x):
        raise RuntimeError("Windows produced no audio for that text.")
    peak = float(np.max(np.abs(x)))
    return x * (0.8 / peak) if peak > 0 else x


def apply_effect(x: np.ndarray, preset: str) -> np.ndarray:
    """Run the effects preset over the speech offline, block by block like live."""
    from .presets import build_chain
    chain = build_chain(preset, TTS_SR, gate_db=None)
    out = np.empty_like(x)
    for i in range(0, len(x), 512):
        out[i:i + 512] = chain.process(x[i:i + 512])
    return np.clip(out, -1, 1)
