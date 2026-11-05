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
| "Is there a new version?" | api.github.com (this repo's latest release) | At most once a day; off with Offline mode or `VOICEFORK_NO_UPDATE_CHECK=1` | `voicefork/updates.py` |
| Python packages | pypi.org, download.pytorch.org | Setup, by `Start Voicefork.bat` | `Start Voicefork.bat` |

There is no account, no analytics and no telemetry of our own. Buttons like *Download VB-CABLE*
just open a web page in your browser.

### Offline mode

Once your voices are downloaded, turn on **Offline mode** (click the device row at the top of the
window → *Privacy*). Voicefork then can't connect to anything outside your PC: every outgoing
connection and DNS lookup is refused in Python's network layer, which every library Voicefork
uses for the internet goes through, and proxy settings are switched off so nothing can be
forwarded either. Update checks and downloads stop; everything already downloaded keeps working. The device row shows "offline" while it's on.
You can also force it for one start with the environment variable `VOICEFORK_OFFLINE=1`.
Code: `voicefork/net.py`, tested in `tests/test_net.py`.

## Verify it yourself

You don't have to trust this page. Here's how to check it on your own PC.
In these tools Voicefork shows up as **python.exe** or **pythonw.exe** from the
`.venv\Scripts\` folder inside your Voicefork folder.

**What you should see**

| When | Connections from Voicefork |
|---|---|
| Live: voice changing, soundboard, hotkeys | None |
| App start | At most one to `api.github.com` per day (update check) |
| *Get voices*, first AI voice, first *Make my voice* | `huggingface.co` and its download servers, only while it downloads |
| Offline mode on | None at all, not even DNS |

**With Portmaster** (free, open source, shows connections per app):

1. Install it from [safing.io/portmaster](https://safing.io/portmaster/) and open it.
2. Start Voicefork, go live, switch a few voices, play a soundboard clip.
3. In Portmaster, open **Apps**, find **pythonw** (or python) with your Voicefork folder in its path,
   and look at its **Connections**. Compare them with the table above.
4. Turn on Offline mode, restart Voicefork, do the same again: the list should stay empty.

**With Wireshark** (free, captures every packet on your network adapter):

1. Install it from [wireshark.org](https://www.wireshark.org/), close other apps that use the
   internet, and start a capture on your network adapter.
2. Use Voicefork as above, then stop the capture.
3. Filter with `dns or tls.handshake.extensions_server_name`. Lookups or connections for
   `huggingface.co` or `api.github.com` should only appear in the moments from the table above;
   with Offline mode on, there should be none.

**Virus scans:** every release zip is uploaded to [VirusTotal](https://www.virustotal.com/); the
report for each release is linked in its release notes. A few scanners may flag the launcher (it
installs Python packages) or the hotkey listener; those are false positives, and the code for both
is here to read.

**Independent checks:** if you've checked Voicefork with these tools, post your screenshots in the
[Discord](https://discord.gg/r2d7wHQtwB) and they'll be added here, with credit.

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
