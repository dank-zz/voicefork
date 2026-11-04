# Security and privacy

Voicefork runs entirely on your PC. This page lists everything it touches so you can check it
against the code yourself. If you find something that doesn't match, please
[open an issue](https://github.com/Dank-zz/voicefork/issues) or report it privately (below).

## Network

Voicefork never uploads your audio, recordings, keystrokes or files. It only downloads:

| What | From | When | Code |
|---|---|---|---|
| AI base models (HuBERT, RMVPE) | huggingface.co/lj1995/VoiceConversionWebUI | First use of AI voices | `voicefork/ai/assets.py` |
| Starter voices | huggingface.co/Nekochu/RVC-VCTK_Voice-sample | When you click to get them | `voicefork/ai/assets.py` |
| Voices you search for, preview or install | huggingface.co | Only in the *Get voices* window | `voicefork/ai/catalog.py`, `voicefork/ai/preview.py` |
| Training base models | huggingface.co/lj1995/VoiceConversionWebUI | First *Make my voice* run | `voicefork/ai/training.py` |
| "Is there a new version?" | api.github.com (this repo's latest release) | At most once a day; off with `VOICEFORK_NO_UPDATE_CHECK=1` | `voicefork/updates.py` |
| Python packages | pypi.org, download.pytorch.org | Setup, by `Start Voicefork.bat` | `Start Voicefork.bat` |

There is no account, no analytics and no telemetry of our own. Buttons like *Download VB-CABLE*
just open a web page in your browser.

## Keyboard and mouse (hotkeys)

Hotkeys and push-to-talk have to work while a game is focused, so Voicefork listens to keys and
the two mouse side buttons system-wide (the `pynput` library). It only checks whether the keys
held right now match one of **your** hotkeys, and forgets each key when you release it. Keys are
never logged, saved or sent anywhere. See `_press` / `_release` in `voicefork/hotkeys.py`.
If you set no hotkeys, nothing ever matches.

## Files it writes

- `%USERPROFILE%\.voicefork\`: models, voices, soundboard clips, training recordings.
- Settings (devices, hotkeys, mode) in the registry under `HKCU\Software\voicefork\voicefork`, via Qt's standard settings store.
- `crash-log.txt` in the app folder: error messages only, so you can report bugs.
- A *Voicefork* shortcut on your desktop and in your Start menu, made once with Windows' own
  shortcut API (`voicefork/shortcut.py`).
- `.venv\` in the app folder: the Python packages the launcher installs.

## Other programs it runs

- `pip`, from `Start Voicefork.bat`, to install the packages in `requirements*.txt`.
- The vendored RVC training scripts in a separate Python process, only when you train a voice
  (`voicefork/ai/training.py`).
- `taskkill` on that training process, only if you press *Stop* during training.

## Voice files

Voice models (`.pth`) from the internet can contain code. Voicefork loads them with
`torch.load(weights_only=True)`, which refuses anything except plain model weights, so a
malicious voice file can't run code (`voicefork/ai/rvc.py`, `voicefork/ai/catalog.py`).

## Third-party code

`voicefork/ai/rvc_lib/` and `voicefork/ai/trainer/` are vendored from
[RVC-Project](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) (MIT,
copyright liujing04, RVC's original developer). The changes made are listed in
`voicefork/ai/trainer/README.md`.

## Reporting a vulnerability

Use GitHub's **Security → Report a vulnerability** on this repo for anything that shouldn't be public.
Please include the file and line.
