RVC training code, vendored from RVC-Project/Retrieval-based-Voice-Conversion-WebUI
(commit 81eed5e, MIT licence, see LICENSE-RVC). Run as separate processes by
voicefork/ai/training.py with this folder on PYTHONPATH.

Changes from upstream (search for "voicefork"):
- i18n: English only, locale file found relative to the module
- infer/audio.py: soundfile loader instead of ffmpeg/av (inputs are WAV)
- infer/hubert.py, train/dataset/extract_f0.py: model paths from VF_HUBERT_DIR / VF_RMVPE
- train/train.py: tensorboard and matplotlib optional
- train/train_index.py, extract_f0.py: sklearn / parselmouth imported only when used
