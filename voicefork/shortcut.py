"""Desktop and Start-menu shortcuts on Windows, so Voicefork opens like any other app.

Made with Windows' built-in shortcut API. The shortcut points at "Start Voicefork.bat" (minimised), which keeps packages in step
after an update and then opens the app without a console window.
Run again any time with:  python -m voicefork shortcut   (e.g. after moving the folder)
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
LAUNCHER = APP_DIR / "Start Voicefork.bat"
ICON = Path(__file__).resolve().parent / "icon.ico"
NAME = "Voicefork"


def targets(desktop: bool = True, start_menu: bool = True) -> list[Path]:
    """Where the .lnk files go: the user's own Desktop and Start-menu Programs folders."""
    import ctypes
    from ctypes import wintypes
    out = []
    for want, csidl in ((desktop, 0x10), (start_menu, 0x02)):   # CSIDL_DESKTOPDIRECTORY, CSIDL_PROGRAMS
        if want:
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
            out.append(Path(buf.value) / f"{NAME}.lnk")
    return out


def create(desktop: bool = True, start_menu: bool = True) -> str:
    """Make the shortcuts with Windows' own shortcut API (no scripts, no PowerShell)."""
    if sys.platform != "win32":
        return "Shortcuts are only made on Windows."
    if not LAUNCHER.is_file():
        return f"Can't find {LAUNCHER.name} next to the app."
    try:
        from comtypes.client import CreateObject
    except ImportError:
        return ("Couldn't make the shortcut: the 'comtypes' package is missing. "
                "Start Voicefork with Start Voicefork.bat once (it installs it), "
                "or run:  .venv\\Scripts\\python -m pip install comtypes")
    try:
        shell = CreateObject("WScript.Shell", dynamic=True)
        made = []
        for lnk_path in targets(desktop, start_menu):
            lnk = shell.CreateShortcut(str(lnk_path))
            lnk.TargetPath = str(LAUNCHER)
            lnk.WorkingDirectory = str(APP_DIR)
            lnk.IconLocation = f"{ICON},0"
            lnk.WindowStyle = 7          # minimised: no console flash
            lnk.Description = "Voicefork: free, open-source voice changer"
            lnk.Save()
            made.append(lnk_path)
    except Exception as e:  # noqa: BLE001
        return f"Couldn't make the shortcut: {e}"
    where = " and ".join(p for p, on in (("desktop", desktop), ("Start menu", start_menu)) if on)
    return f"Voicefork shortcut added to your {where}."
