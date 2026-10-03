"""Linux (X11) native keyboard injection via the XTEST extension
(python-xlib, pure Python, no system package compile needed). This is the
standard, root-free way to synthesize input on X11, and works under Xvfb
(what CI's ubuntu-latest leg uses).

Wayland is explicitly NOT covered here: XTEST has no Wayland equivalent,
and the honest options there (ydotool via uinput, which needs root or a
group membership; or the libei/xdg-desktop-portal RemoteDesktop path,
which prompts the user interactively) are both a different enough shape
that they belong in their own module, not bolted onto this one. See
GAP_ANALYSIS.md.

UNVERIFIED ON REAL LINUX HARDWARE: written and reviewed, not interactively
tested (no Linux desktop available this session). CI (ubuntu-latest under
Xvfb) is the only verification channel.
"""

from __future__ import annotations

import time

from Xlib import X
from Xlib.display import Display
from Xlib.ext import xtest
from Xlib.XK import string_to_keysym

MODIFIER_KEYSYMS: dict[str, str] = {
    "ctrl": "Control_L",
    "control": "Control_L",
    "alt": "Alt_L",
    "shift": "Shift_L",
    "super": "Super_L",
    "win": "Super_L",
    "cmd": "Super_L",
}

# Keys whose X11 keysym name differs from the chord string openreach uses.
_KEYSYM_ALIASES: dict[str, str] = {
    "return": "Return",
    "enter": "Return",
    "escape": "Escape",
    "tab": "Tab",
    "space": "space",
    "backspace": "BackSpace",
    "delete": "Delete",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pagedown": "Next",
    "minus": "minus",
    "equal": "equal",
    "comma": "comma",
    "period": "period",
    "slash": "slash",
    "semicolon": "semicolon",
    "quote": "apostrophe",
    "leftbracket": "bracketleft",
    "rightbracket": "bracketright",
    "backslash": "backslash",
}


class UnknownKeyError(KeyError):
    """Raised on an unmapped key name, never silently dropped."""


def _display() -> Display:
    # A fresh connection per call keeps this module stateless like its
    # macOS/Windows siblings; XTEST calls are cheap enough that connection
    # reuse isn't worth the lifecycle complexity for a one-shot CLI.
    return Display()


def _keysym_for(key_name: str) -> int:
    name = _KEYSYM_ALIASES.get(key_name, key_name)
    if len(name) == 1 and name.isalpha():
        name = name.lower() if name.islower() else name
    keysym = string_to_keysym(name)
    if keysym == 0:
        raise UnknownKeyError(f"unmapped key {key_name!r}; not a known X11 keysym")
    return keysym


def _keycode_for(display: Display, keysym: int) -> int:
    keycode = display.keysym_to_keycode(keysym)
    if keycode == 0:
        raise UnknownKeyError(f"keysym {keysym} has no keycode on this X server's current keymap")
    return keycode


def press_chord(chord: str) -> None:
    """Press a key or modifier chord, e.g. "ctrl+a", "ctrl+shift+s",
    "escape". Modifiers are pressed in order, the main key is pressed and
    released, then modifiers release in reverse, always via try/finally,
    the same stuck-key safety as the macOS and Windows backends.
    """
    parts = [p.strip().lower() for p in chord.split("+")]
    *modifier_names, key_name = parts

    display = _display()
    try:
        modifier_keycodes: list[int] = []
        for mod in modifier_names:
            if mod not in MODIFIER_KEYSYMS:
                raise UnknownKeyError(f"unknown modifier {mod!r} in chord {chord!r}")
            keysym = string_to_keysym(MODIFIER_KEYSYMS[mod])
            modifier_keycodes.append(_keycode_for(display, keysym))

        if key_name in MODIFIER_KEYSYMS and not modifier_names:
            keysym = string_to_keysym(MODIFIER_KEYSYMS[key_name])
            keycode = _keycode_for(display, keysym)
            xtest.fake_input(display, X.KeyPress, keycode)
            display.sync()
            time.sleep(0.02)
            xtest.fake_input(display, X.KeyRelease, keycode)
            display.sync()
            return

        main_keysym = _keysym_for(key_name)
        main_keycode = _keycode_for(display, main_keysym)

        pressed: list[int] = []
        try:
            for keycode in modifier_keycodes:
                xtest.fake_input(display, X.KeyPress, keycode)
                display.sync()
                pressed.append(keycode)
                time.sleep(0.01)
            xtest.fake_input(display, X.KeyPress, main_keycode)
            display.sync()
            time.sleep(0.02)
            xtest.fake_input(display, X.KeyRelease, main_keycode)
            display.sync()
        finally:
            for keycode in reversed(pressed):
                xtest.fake_input(display, X.KeyRelease, keycode)
                display.sync()
                time.sleep(0.01)
    finally:
        display.close()


def type_text(text: str, interval: float = 0.012) -> None:
    """Type literal text by resolving each character to a keysym and
    keycode. Characters with no keysym (most non-Latin scripts, some
    symbols) raise UnknownKeyError rather than being silently dropped;
    full Unicode input on X11 needs a different mechanism (XIM or a
    temporary keymap remap) not implemented here, a real, named gap, not
    a hidden one. See GAP_ANALYSIS.md.
    """
    display = _display()
    try:
        for char in text:
            keysym = string_to_keysym(char)
            if keysym == 0:
                raise UnknownKeyError(f"no X11 keysym for character {char!r}; non-ASCII typing is not supported yet")
            keycode = _keycode_for(display, keysym)
            xtest.fake_input(display, X.KeyPress, keycode)
            display.sync()
            xtest.fake_input(display, X.KeyRelease, keycode)
            display.sync()
            time.sleep(interval)
    finally:
        display.close()
