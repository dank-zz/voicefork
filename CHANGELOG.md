# Changelog

## v0.1.4.1

- **Fixed first-time setup closing instantly on a fresh download** ("and was unexpected at this time" - a black window that flashed and vanished). The new Python 3.10 - 3.13 check broke the launcher before anything was installed, so nothing ever got set up. Setup now runs correctly on the first try. If you were stuck on this, download v0.1.4.1 and run it again.

## v0.1.4

**Setup is more reliable**

- **Fixed "The system cannot find the batch label specified - visible"** that could stop first-time setup. The launcher was stored with Unix line endings, which keeps Windows from finding labels inside a batch file. A `.gitattributes` now keeps `.bat` files as CRLF, so the download works as-is.
- **Fixed setup failing with "Could not open requirements file: 'requirements.txt'"** when Voicefork was started from a shortcut or a synced (OneDrive) folder. The launcher now uses absolute paths for everything it installs.
- **Python 3.10 - 3.13 are all accepted now** (3.12 still recommended), not just 3.12. If you only have the newer Python install manager with no runtime, the launcher installs Python 3.12 for you.

**New: Mic fry**

- A **"Mic fry" slider** on the Effects tab: one knob to compress and over-drive your mic, from clean to blown-out. Works on any PC and with any preset, Clean included.

**Stability**

- **Fixed a crash on some GPUs** with AI voices ("captures_underway.empty() INTERNAL ASSERT FAILED ... CUDACachingAllocator.cpp"). Voicefork now skips CUDA-graph capture when free VRAM is low, turns graphs off for the rest of the session after any capture or replay problem, and warms up without them - so it keeps running (slightly slower) instead of closing. The VRAM guard is tunable with `RVC_CUDA_GRAPH_MIN_FREE_MB`.

**Offline mode**

- You can now **turn Offline mode off inside the app** even when it was switched on by the `VOICEFORK_OFFLINE` environment variable. Turning it off also clears that variable so it stays off next time.

## v0.1.3.1

- Fixed a crash on start ("'_SixMetaPathImporter' object has no attribute '_path'") with newer PySide6 versions
- If hotkeys can't start for any reason, the app now opens anyway and shows "Hotkeys ⚠" with the reason

## v0.1.3

- **Offline mode:** one switch (device row → Privacy) blocks every connection Voicefork could make, including DNS, so you can prove in Portmaster or Wireshark that nothing goes out
- **Verify it yourself:** SECURITY.md shows how to check Voicefork's network traffic with Portmaster and Wireshark, and links each release's VirusTotal scan
- **Plug in a mic or headset while the app is open:** Voicefork now notices by itself and picks it up (when you're not live), plus a Refresh devices button
- Removed Type to speak

## v0.1.2

- Tells you when a new version is out, with a short note about what changed (checks GitHub once a day; can be turned off)
- Updating: unzip the new version over the old folder; the launcher installs new packages only when needed
- Desktop and Start-menu shortcut with the Voicefork icon; opens without a console window
- Errors are saved to crash-log.txt even when started from the shortcut
- SECURITY.md: everything Voicefork downloads, writes and listens to, with the code that does it
- Removed leftover upstream RVC test code (hard-coded paths from the RVC developer's PC) and an unused git call
- Shortcuts are made with Windows' own shortcut API instead of PowerShell
- README: requirements section and a link to the Voicefork Discord; clearer Mode tooltip, including Laptop mode

## v0.1.0 (first public release)

- Real-time AI voices (RVC) with free starter voices, a Hugging Face voice browser and previews
- Make your own voice: guided recording or import, train in-app (Quick / Standard / Best)
- Blend two voices into a new one
- 11 effect presets, soundboard, type to speak, hotkeys and push-to-talk
- Auto speed test with Fast / Balanced / Crisp / Laptop modes
- Virtual mic setup guide, one-click Windows launcher
