"""Windows shortcuts, with a fake Windows shortcut API (works on any OS)."""
import sys
import types
from pathlib import Path

from voicefork import shortcut


class FakeLnk:
    saved = []

    def __init__(self, path):
        self.path = path

    def Save(self):
        FakeLnk.saved.append(self)


def fake_windows(monkeypatch, tmp_path):
    FakeLnk.saved = []
    shell = types.SimpleNamespace(CreateShortcut=FakeLnk)
    client = types.ModuleType("comtypes.client")
    client.CreateObject = lambda name, dynamic=False: shell
    monkeypatch.setitem(sys.modules, "comtypes", types.ModuleType("comtypes"))
    monkeypatch.setitem(sys.modules, "comtypes.client", client)
    monkeypatch.setattr(shortcut.sys, "platform", "win32")
    monkeypatch.setattr(shortcut, "targets", lambda d=True, s=True:
                        [tmp_path / n for n, on in (("Desktop.lnk", d), ("Programs.lnk", s)) if on])
    app = tmp_path / "O'Neil apps" / "voicefork"
    app.mkdir(parents=True)
    (app / "Start Voicefork.bat").write_text("@echo off")
    monkeypatch.setattr(shortcut, "APP_DIR", app)
    monkeypatch.setattr(shortcut, "LAUNCHER", app / "Start Voicefork.bat")
    monkeypatch.setattr(shortcut, "ICON", app / "voicefork" / "icon.ico")
    return app


def test_makes_desktop_and_start_menu_shortcuts(monkeypatch, tmp_path):
    app = fake_windows(monkeypatch, tmp_path)
    msg = shortcut.create()
    assert "desktop and Start menu" in msg
    assert len(FakeLnk.saved) == 2
    lnk = FakeLnk.saved[0]
    assert lnk.TargetPath == str(app / "Start Voicefork.bat")
    assert lnk.WorkingDirectory == str(app)
    assert lnk.IconLocation.endswith("icon.ico,0")
    assert lnk.WindowStyle == 7


def test_only_desktop(monkeypatch, tmp_path):
    fake_windows(monkeypatch, tmp_path)
    shortcut.create(desktop=True, start_menu=False)
    assert [l.path for l in FakeLnk.saved] == [str(tmp_path / "Desktop.lnk")]


def test_icon_is_shipped():
    ico = Path(shortcut.__file__).with_name("icon.ico")
    assert ico.is_file() and ico.read_bytes()[:4] == b"\x00\x00\x01\x00"   # ICO header


def test_not_windows_is_harmless(monkeypatch):
    monkeypatch.setattr(shortcut.sys, "platform", "linux")
    assert "only" in shortcut.create()


def test_no_powershell_or_scripts():
    src = Path(shortcut.__file__).read_text().lower()
    assert "subprocess" not in src and "\"powershell\"" not in src and "os.system" not in src


def test_missing_comtypes_says_how_to_fix(monkeypatch, tmp_path):
    fake_windows(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, "comtypes.client", None)     # import fails
    msg = shortcut.create()
    assert "comtypes" in msg and "pip install comtypes" in msg
