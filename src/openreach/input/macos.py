"""macOS native keyboard injection via Quartz CGEvent, replacing pyautogui's
hotkey()/typewrite() for reliability.

The bug this fixes, confirmed live: pyautogui's macOS backend
(_pyautogui_osx._normalKeyEvent) posts a chord's modifier key and main key
as SEPARATE CGEventCreateKeyboardEvent calls with a ~10ms gap and never
calls CGEventSetFlags. Whether the OS still considers the modifier held by
the time the main key's event is processed is a race. Live symptom this
session: `pyautogui.hotkey('cmd', 'a')` typed a literal "a" character
instead of selecting all.

The fix, already proven in this toolchain (~/Developer/logic-mcp's
input.py, written independently for a different app): set the modifier
flags directly on the key event itself via CGEventSetFlags, so the OS
receives one event that IS a Cmd+A, not two events that might race.
"""

from __future__ import annotations

import time

import Quartz

# US ANSI virtual keycodes. Covers the common case; unmapped keys raise
# rather than silently no-op (the class of bug this module exists to kill).
KEY_CODES: dict[str, int] = {
    "a": 0x00,
    "s": 0x01,
    "d": 0x02,
    "f": 0x03,
    "h": 0x04,
    "g": 0x05,
    "z": 0x06,
    "x": 0x07,
    "c": 0x08,
    "v": 0x09,
    "b": 0x0B,
    "q": 0x0C,
    "w": 0x0D,
    "e": 0x0E,
    "r": 0x0F,
    "y": 0x10,
    "t": 0x11,
    "1": 0x12,
    "2": 0x13,
    "3": 0x14,
    "4": 0x15,
    "6": 0x16,
    "5": 0x17,
    "equal": 0x18,
    "9": 0x19,
    "7": 0x1A,
    "minus": 0x1B,
    "8": 0x1C,
    "0": 0x1D,
    "rightbracket": 0x1E,
    "o": 0x1F,
    "u": 0x20,
    "leftbracket": 0x21,
    "i": 0x22,
    "p": 0x23,
    "l": 0x25,
    "j": 0x26,
    "quote": 0x27,
    "k": 0x28,
    "semicolon": 0x29,
    "backslash": 0x2A,
    "comma": 0x2B,
    "slash": 0x2C,
    "n": 0x2D,
    "m": 0x2E,
    "period": 0x2F,
    "tab": 0x30,
    "space": 0x31,
    "backtick": 0x32,
    "delete": 0x33,
    "escape": 0x35,
    "return": 0x24,
    "enter": 0x24,
    "left": 0x7B,
    "right": 0x7C,
    "down": 0x7D,
    "up": 0x7E,
    "home": 0x73,
    "end": 0x77,
    "pageup": 0x74,
    "pagedown": 0x79,
    "forwarddelete": 0x75,
    "f1": 0x7A,
    "f2": 0x78,
    "f3": 0x63,
    "f4": 0x76,
    "f5": 0x60,
    "f6": 0x61,
    "f7": 0x62,
    "f8": 0x64,
    "f9": 0x65,
    "f10": 0x6D,
    "f11": 0x67,
    "f12": 0x6F,
}
KEY_CODES["backspace"] = KEY_CODES["delete"]

MODIFIER_FLAGS: dict[str, int] = {
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "command": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "opt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
}

# A keystroke pair's up/down gap. logic-mcp uses 0.03s for an app that
# needed extra settle time; 0.02s is the floor that reproduced reliably
# against TextEdit and Spotlight in this session's manual testing.
KEY_EVENT_GAP_S = 0.02


_ALL_MODIFIER_FLAGS = (
    Quartz.kCGEventFlagMaskCommand
    | Quartz.kCGEventFlagMaskShift
    | Quartz.kCGEventFlagMaskAlternate
    | Quartz.kCGEventFlagMaskControl
)


def clear_stuck_modifiers(retries: int = 5, retry_delay: float = 0.05) -> bool:
    """Force-release any modifier the HID system thinks is still held, and
    verify it actually worked before returning, retrying if not.

    Found live this session: an interrupted raw pyautogui.hotkey() call
    (modifier down and up are separate events there) left Cmd stuck held
    at the OS level, system-wide, well after the call returned. Every
    subsequent keystroke from any source, not just this tool, was then
    misread as a Cmd-chord. This module's own press_chord() never posts a
    standalone modifier keydown, so it can't cause this, but it calls this
    defensively before every chord anyway, in case something else did.

    A single fire-and-forget attempt was tried first and measured
    unreliable: a test that deliberately stuck Cmd and then called this
    once still read Cmd as held immediately after, because the clearing
    event hadn't been processed by the time the next read ran. Returns
    whether the clear was confirmed, so a caller can decide whether to
    proceed or abort rather than silently typing into a corrupted state.
    """
    for _ in range(retries):
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
        if not (flags & _ALL_MODIFIER_FLAGS):
            return True
        event = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventSetType(event, Quartz.kCGEventFlagsChanged)
        Quartz.CGEventSetFlags(event, 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(retry_delay)
    flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
    return not (flags & _ALL_MODIFIER_FLAGS)


class UnknownKeyError(KeyError):
    """Raised on an unmapped key name, never silently dropped."""


class StuckModifierError(RuntimeError):
    """Raised when a prior stuck modifier could not be cleared. Fail
    closed: proceeding would risk every keystroke in this call being
    misread as a chord, exactly the bug this module exists to prevent.
    """


def press_chord(chord: str) -> None:
    """Press a key or modifier chord, e.g. "cmd+a", "cmd+shift+q", "escape".
    Sets all modifier flags directly on the single main-key event pair
    (down, then up), which is the fix for the race pyautogui has.
    """
    if not clear_stuck_modifiers():
        raise StuckModifierError("a modifier key is stuck held at the OS level and could not be cleared")
    parts = [p.strip().lower() for p in chord.split("+")]
    *modifier_names, key_name = parts

    flags = 0
    for mod in modifier_names:
        if mod not in MODIFIER_FLAGS:
            raise UnknownKeyError(f"unknown modifier {mod!r} in chord {chord!r}")
        flags |= MODIFIER_FLAGS[mod]

    if key_name in MODIFIER_FLAGS and not modifier_names:
        # A bare modifier (e.g. "shift" alone) has no non-modifier key to
        # carry it, so synthesize a flags-changed event pair instead.
        _press_bare_modifier(key_name)
        return

    if key_name not in KEY_CODES:
        raise UnknownKeyError(f"unmapped key {key_name!r} in chord {chord!r}; add it to KEY_CODES")

    code = KEY_CODES[key_name]
    for is_down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, code, is_down)
        if flags:
            Quartz.CGEventSetFlags(event, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(KEY_EVENT_GAP_S)
    if flags:
        # Measured live: setting flags on a regular key's down/up pair can
        # still leave the OS's persistent HID modifier state latched after
        # the pair completes, not just on an interrupted call. Clearing
        # unconditionally after every modified chord, not only defensively
        # before one, is what actually kept this from recurring.
        clear_stuck_modifiers()


def _press_bare_modifier(mod_name: str) -> None:
    flag = MODIFIER_FLAGS[mod_name]
    down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
    Quartz.CGEventSetType(down, Quartz.kCGEventFlagsChanged)
    Quartz.CGEventSetFlags(down, flag)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(KEY_EVENT_GAP_S)
    up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
    Quartz.CGEventSetType(up, Quartz.kCGEventFlagsChanged)
    Quartz.CGEventSetFlags(up, 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    time.sleep(KEY_EVENT_GAP_S)


def type_text(text: str, interval: float = 0.012) -> None:
    """Type literal Unicode text via CGEventKeyboardSetUnicodeString, which
    sidesteps the keycode map entirely (works for any character, not just
    the ones in KEY_CODES). This is also the pattern logic-mcp uses.
    """
    if not clear_stuck_modifiers():
        raise StuckModifierError("a modifier key is stuck held at the OS level and could not be cleared")
    for char in text:
        down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(char), char)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(char), char)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        time.sleep(interval)
