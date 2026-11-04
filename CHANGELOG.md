# Changelog

## v0.1.1

- Tells you when a new version is out, with a short note about what changed (checks GitHub once a day; can be turned off)
- Updating: unzip the new version over the old folder; the launcher installs new packages only when needed
- Desktop and Start-menu shortcut with the Voicefork icon; opens without a console window
- Errors are saved to crash-log.txt even when started from the shortcut
- SECURITY.md: everything Voicefork downloads, writes and listens to, with the code that does it
- Removed leftover upstream RVC test code (hard-coded paths from the RVC developer's PC) and an unused git call
- Shortcuts are made with Windows' own shortcut API instead of PowerShell

## v0.1.0 (first public release)

- Real-time AI voices (RVC) with free starter voices, a Hugging Face voice browser and previews
- Make your own voice: guided recording or import, train in-app (Quick / Standard / Best)
- Blend two voices into a new one
- 11 effect presets, soundboard, type to speak, hotkeys and push-to-talk
- Auto speed test with Fast / Balanced / Crisp / Laptop modes
- Virtual mic setup guide, one-click Windows launcher
