"""voicefork: minimal replacement for RVC's ffmpeg/torchaudio audio loader.

The app converts every training file to WAV before training starts, so plain
soundfile + polyphase resampling is enough and saves the ffmpeg/av dependencies.
"""
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def clean_path(path_str):
    return str(path_str).strip(" ").strip('"').strip("\n").strip('"').strip(" ")


def load_audio(file, sr, force_mono=True):
    data, file_sr = sf.read(clean_path(file), dtype="float32", always_2d=True)
    data = data.mean(axis=1) if force_mono else data.T
    if file_sr != sr:
        g = np.gcd(int(file_sr), int(sr))
        data = resample_poly(data, sr // g, file_sr // g, axis=-1).astype(np.float32)
    return np.ascontiguousarray(data, dtype=np.float32)
