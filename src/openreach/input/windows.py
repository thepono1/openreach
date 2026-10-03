"""Windows native keyboard injection via SendInput (ctypes, stdlib only,
no comtypes/pywinauto dependency needed for basic key/text injection).

Unlike macOS, Windows has no single-event "set modifier flags atomically"
trick (CGEventSetFlags has no Win32 equivalent): a chord is genuinely sent
as separate keydown events for each modifier, then the main key, then
released in reverse order. That is the correct, standard Win32 pattern,
not a bug to work around. The real risk on this platform is a modifier
left down if an exception fires mid-chord (the Windows equivalent of the
stuck-Cmd bug found on macOS this session), so every chord releases its
keys in a try/finally.

UNVERIFIED ON REAL WINDOWS HARDWARE: this was written and reviewed, not
interactively tested, because no Windows machine was available this
session. CI (windows-latest, live_input tests) is the only verification
channel; see GAP_ANALYSIS.md.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32  # type: ignore[attr-defined]
# Explicit argtypes/restype: ctypes' default marshaling of a bare pointer
# argument can be unreliable on 64-bit Python for this particular API in
# some interpreter builds; declaring them explicitly is the standard,
# defensive fix recommended for SendInput specifically.
user32.SendInput.argtypes = (wintypes.UINT, ctypes.c_void_p, ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# Virtual-key codes. Letters and digits map directly to their ASCII value
# in the Win32 VK space, which keeps this table shorter than macOS's.
KEY_CODES: dict[str, int] = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
KEY_CODES.update({chr(c): c for c in range(ord("0"), ord("9") + 1)})
KEY_CODES.update(
    {
        "tab": 0x09,
        "return": 0x0D,
        "enter": 0x0D,
        "escape": 0x1B,
        "space": 0x20,
        "backspace": 0x08,
        "delete": 0x2E,
        "left": 0x25,
        "up": 0x26,
        "right": 0x27,
        "down": 0x28,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "f1": 0x70,
        "f2": 0x71,
        "f3": 0x72,
        "f4": 0x73,
        "f5": 0x74,
        "f6": 0x75,
        "f7": 0x76,
        "f8": 0x77,
        "f9": 0x78,
        "f10": 0x79,
        "f11": 0x7A,
        "f12": 0x7B,
        "minus": 0xBD,
        "equal": 0xBB,
        "comma": 0xBC,
        "period": 0xBE,
        "slash": 0xBF,
        "semicolon": 0xBA,
        "quote": 0xDE,
        "leftbracket": 0xDB,
        "rightbracket": 0xDD,
        "backslash": 0xDC,
    }
)
# lowercase letters typed as lowercase in a chord string should still map
KEY_CODES.update({k.lower(): v for k, v in list(KEY_CODES.items()) if k.isalpha()})

MODIFIER_VK: dict[str, int] = {
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "cmd": 0x5B,
    "super": 0x5B,  # "cmd" accepted so chord strings are portable across OSes
}


class UnknownKeyError(KeyError):
    """Raised on an unmapped key name, never silently dropped."""


# --- low-level SendInput plumbing -------------------------------------------


# ULONG_PTR, not POINTER(ULONG): dwExtraInfo is an integer-sized-as-a-
# pointer value (almost always 0), never an actual pointer to dereference.
# Using the wrong ctypes type here was part of the original GetLastError=87
# failure on real Windows CI.
_ULONG_PTR = ctypes.c_size_t


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUT_UNION(ctypes.Union):
    # Confirmed root cause of GetLastError=87 on real Windows CI: this
    # union originally only declared `ki`, so ctypes.sizeof(_INPUT) was
    # smaller than the real Win32 INPUT struct (whose union is sized for
    # the larger MOUSEINPUT), and SendInput rejected the mismatched
    # element size. All three members must be present even though only
    # `ki` is ever used, so the struct size matches what SendInput expects.
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


def _send_key_event(vk: int, key_up: bool, unicode_char: str | None = None) -> None:
    flags = KEYEVENTF_KEYUP if key_up else 0
    wvk = vk
    wscan = 0
    if unicode_char is not None:
        flags |= KEYEVENTF_UNICODE
        wvk = 0
        wscan = ord(unicode_char)
    inp = _INPUT(type=INPUT_KEYBOARD, union=_INPUT_UNION(ki=_KEYBDINPUT(wvk, wscan, flags, 0, 0)))
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
    if sent != 1:
        raise OSError(f"SendInput failed (GetLastError={ctypes.GetLastError()})")


# --- public API, mirrors macos.py's shape -----------------------------------


def press_chord(chord: str) -> None:
    """Press a key or modifier chord, e.g. "ctrl+a", "ctrl+shift+s", "escape".
    Modifiers are pressed down in order, the main key is pressed and
    released, then modifiers are released in reverse order, always (even
    on exception) via try/finally, so a failure mid-chord can't leave a
    modifier stuck held, the Windows equivalent of the macOS bug this
    module's sibling fixed.
    """
    parts = [p.strip().lower() for p in chord.split("+")]
    *modifier_names, key_name = parts

    modifier_vks: list[int] = []
    for mod in modifier_names:
        if mod not in MODIFIER_VK:
            raise UnknownKeyError(f"unknown modifier {mod!r} in chord {chord!r}")
        modifier_vks.append(MODIFIER_VK[mod])

    if key_name in MODIFIER_VK and not modifier_names:
        vk = MODIFIER_VK[key_name]
        _send_key_event(vk, key_up=False)
        time.sleep(0.02)
        _send_key_event(vk, key_up=True)
        return

    if key_name not in KEY_CODES:
        raise UnknownKeyError(f"unmapped key {key_name!r} in chord {chord!r}; add it to KEY_CODES")
    main_vk = KEY_CODES[key_name]

    pressed: list[int] = []
    try:
        for vk in modifier_vks:
            _send_key_event(vk, key_up=False)
            pressed.append(vk)
            time.sleep(0.01)
        _send_key_event(main_vk, key_up=False)
        time.sleep(0.02)
        _send_key_event(main_vk, key_up=True)
    finally:
        for vk in reversed(pressed):
            _send_key_event(vk, key_up=True)
            time.sleep(0.01)


def type_text(text: str, interval: float = 0.012) -> None:
    """Type literal Unicode text via KEYEVENTF_UNICODE, sidestepping the
    virtual-key table entirely, the same approach macos.py uses.
    """
    for char in text:
        _send_key_event(0, key_up=False, unicode_char=char)
        _send_key_event(0, key_up=True, unicode_char=char)
        time.sleep(interval)
