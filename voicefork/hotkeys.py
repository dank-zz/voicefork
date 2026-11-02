"""Global hotkeys and push-to-talk.

Keys are listened for system-wide (pynput), so they work while a game has
focus. Bindings are plain strings, the same format everywhere:

    "f1", "ctrl+shift+1", "page_up", "mouse4", "mouse5"

Modifiers are ctrl / alt / shift / cmd (left and right count the same).
pynput calls us from its own threads; we hand everything to the Qt thread via
signals, so no audio or UI code runs on the listener thread.

Note: Windows doesn't deliver keys to an app running without admin rights
while a game running *as admin* has focus. If hotkeys stop working in one
game, run Voicefork as admin too.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal

MODIFIERS = ("ctrl", "alt", "shift", "cmd")
_MOD_ALIASES = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift_l": "shift", "shift_r": "shift", "cmd_l": "cmd", "cmd_r": "cmd",
}


def normalize(binding: str) -> str:
    """'Shift+Ctrl+F1' -> 'ctrl+shift+f1' (modifiers in a fixed order)."""
    parts = [p.strip().lower() for p in binding.split("+") if p.strip()]
    mods = [m for m in MODIFIERS if m in parts]
    keys = [p for p in parts if p not in MODIFIERS]
    return "+".join(mods + keys[-1:])


def pretty(binding: str) -> str:
    if not binding:
        return "—"
    names = {"mouse4": "Mouse 4", "mouse5": "Mouse 5", "page_up": "PgUp", "page_down": "PgDn",
             "caps_lock": "Caps", "space": "Space", "insert": "Ins", "delete": "Del"}
    return " + ".join(names.get(p, p.upper() if len(p) <= 3 else p.capitalize())
                      for p in binding.split("+"))


# ---------------------------------------------------------------- key names
def pynput_key_name(key) -> str | None:
    """pynput Key/KeyCode -> our name."""
    from pynput import keyboard
    if isinstance(key, keyboard.Key):
        return _MOD_ALIASES.get(key.name, key.name)
    vk = getattr(key, "vk", None)
    if vk is not None:  # use the virtual key so shift/ctrl don't change '1' into '!' or '\x01'
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            return chr(vk).lower()
        if 0x60 <= vk <= 0x69:
            return f"num{vk - 0x60}"
    ch = getattr(key, "char", None)
    return ch.lower() if ch else None


_QT_NAMES = {
    Qt.Key_Space: "space", Qt.Key_Tab: "tab", Qt.Key_Return: "enter", Qt.Key_Enter: "enter",
    Qt.Key_Backspace: "backspace", Qt.Key_Insert: "insert", Qt.Key_Delete: "delete",
    Qt.Key_Home: "home", Qt.Key_End: "end", Qt.Key_PageUp: "page_up", Qt.Key_PageDown: "page_down",
    Qt.Key_Up: "up", Qt.Key_Down: "down", Qt.Key_Left: "left", Qt.Key_Right: "right",
    Qt.Key_CapsLock: "caps_lock", Qt.Key_Pause: "pause", Qt.Key_ScrollLock: "scroll_lock",
    Qt.Key_Print: "print_screen", Qt.Key_Menu: "menu",
}
_QT_MODS = {Qt.Key_Control: "ctrl", Qt.Key_Shift: "shift", Qt.Key_Alt: "alt", Qt.Key_Meta: "cmd"}


def qt_key_name(event) -> str | None:
    """QKeyEvent -> our binding string (None while only a modifier is down)."""
    k = event.key()
    if k in _QT_MODS:
        return None
    if Qt.Key_F1 <= k <= Qt.Key_F24:
        name = f"f{k - Qt.Key_F1 + 1}"
    elif event.modifiers() & Qt.KeypadModifier and Qt.Key_0 <= k <= Qt.Key_9:
        name = f"num{k - Qt.Key_0}"
    elif Qt.Key_0 <= k <= Qt.Key_9 or Qt.Key_A <= k <= Qt.Key_Z:
        name = chr(k).lower()
    else:
        name = _QT_NAMES.get(k)
        if name is None:
            return None
    m = event.modifiers()
    mods = [n for flag, n in ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
                              (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "cmd")) if m & flag]
    return "+".join(mods + [name])


def qt_mouse_name(event) -> str | None:
    return {Qt.BackButton: "mouse4", Qt.ForwardButton: "mouse5"}.get(event.button())


# ---------------------------------------------------------------- manager
class HotkeyManager(QObject):
    """Watches global keys. Emits `action(id)` for bound keys and `ptt(bool)` for push-to-talk."""
    action = Signal(str)
    ptt = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bindings: dict[str, str] = {}   # binding string -> action id
        self.ptt_binding = ""
        self.paused = False                  # while the user is assigning a key
        self._mods: set[str] = set()
        self._down: set[str] = set()
        self._ptt_held = False
        self._kb = self._mouse = None
        self.error: str | None = None

    def set_bindings(self, bindings: dict[str, str], ptt_binding: str):
        """bindings: action id -> binding string."""
        self.bindings = {normalize(b): a for a, b in bindings.items() if b}
        self.ptt_binding = normalize(ptt_binding) if ptt_binding else ""

    def start(self) -> bool:
        try:
            from pynput import keyboard, mouse
        except ImportError:
            self.error = "Hotkeys need the pynput package:  .venv\\Scripts\\python -m pip install pynput"
            return False
        self._kb = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse = mouse.Listener(on_click=self._on_click)
        self._kb.daemon = self._mouse.daemon = True
        self._kb.start()
        self._mouse.start()
        return True

    def stop(self):
        for listener in (self._kb, self._mouse):
            if listener is not None:
                listener.stop()

    # --- listener threads ---------------------------------------------------
    def _combo(self, name: str) -> str:
        return "+".join([m for m in MODIFIERS if m in self._mods] + [name])

    def _ptt_matches(self, name: str, combo: str) -> bool:
        # PTT is usually a single key held while also pressing others, so match the bare key too
        return bool(self.ptt_binding) and self.ptt_binding in (combo, name)

    def _press(self, name: str):
        if name in MODIFIERS:
            self._mods.add(name)
            return
        if name in self._down:      # auto-repeat while held
            return
        self._down.add(name)
        if self.paused:
            return
        combo = self._combo(name)
        if self._ptt_matches(name, combo) and not self._ptt_held:
            self._ptt_held = True
            self.ptt.emit(True)
        act = self.bindings.get(combo)
        if act:
            self.action.emit(act)

    def _release(self, name: str):
        if name in MODIFIERS:
            self._mods.discard(name)
            return
        self._down.discard(name)
        if self._ptt_held and self.ptt_binding.split("+")[-1] == name:
            self._ptt_held = False
            self.ptt.emit(False)

    def _on_press(self, key):
        name = pynput_key_name(key)
        if name:
            self._press(name)

    def _on_release(self, key):
        name = pynput_key_name(key)
        if name:
            self._release(name)

    def _on_click(self, _x, _y, button, pressed):
        name = {"x1": "mouse4", "x2": "mouse5"}.get(getattr(button, "name", ""))
        if name:
            (self._press if pressed else self._release)(name)
