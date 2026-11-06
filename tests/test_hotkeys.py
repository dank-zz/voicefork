"""Hotkey matching and push-to-talk, without a real keyboard. Needs PySide6 (skipped otherwise)."""
import pytest

pytest.importorskip("PySide6")

from voicefork.hotkeys import HotkeyManager, normalize, pretty  # noqa: E402


def test_normalize_orders_modifiers():
    assert normalize("Shift+Ctrl+F1") == "ctrl+shift+f1"
    assert normalize("mouse4") == "mouse4"


def test_pretty():
    assert pretty("ctrl+shift+f1") == "CTRL + SHIFT + F1"
    assert pretty("mouse4") == "Mouse 4"
    assert pretty("") == "—"


def make():
    m = HotkeyManager()
    fired, ptt = [], []
    m.action.connect(fired.append)
    m.ptt.connect(ptt.append)
    return m, fired, ptt


def test_action_fires_once_despite_key_repeat():
    m, fired, _ = make()
    m.set_bindings({"preset:robot": "f2"}, "")
    for _ in range(5):
        m._press("f2")          # held key auto-repeats
    m._release("f2")
    assert fired == ["preset:robot"]


def test_modifier_combo_must_match():
    m, fired, _ = make()
    m.set_bindings({"voice:Nova": "ctrl+1"}, "")
    m._press("1"); m._release("1")
    m._press("ctrl"); m._press("1"); m._release("1"); m._release("ctrl")
    assert fired == ["voice:Nova"]


def test_push_to_talk_hold_and_release_even_with_other_keys():
    m, _, ptt = make()
    m.set_bindings({}, "mouse4")
    m._press("mouse4")
    m._press("w"); m._press("shift")    # moving / sprinting in a game while talking
    m._release("w")
    m._release("mouse4")
    assert ptt == [True, False]


def test_paused_while_assigning():
    m, fired, ptt = make()
    m.set_bindings({"preset:cave": "f5"}, "v")
    m.paused = True
    m._press("f5"); m._press("v")
    assert fired == [] and ptt == []


def test_broken_pynput_does_not_crash(monkeypatch):
    """A pynput that fails to import with something other than ImportError (seen with
    some PySide6 + six combinations) turns hotkeys off instead of crashing the app."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pynput" or name.startswith("pynput."):
            raise AttributeError("'_SixMetaPathImporter' object has no attribute '_path'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    m = HotkeyManager()
    assert m.start() is False
    assert "Hotkeys are off" in m.error and "AttributeError" in m.error
