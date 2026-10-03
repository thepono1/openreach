"""Focus verification: the gap behind every "typed into the wrong window"
failure this session. mirroir's lessons #9/#17/#18 put it precisely:
"ready is a claim, the screenshot is the evidence." This module makes that
check cheap enough that a harness has no excuse to skip it before type/key.

Only macOS is implemented live (NSWorkspace); Windows and Linux have
documented, reviewed-but-unverified implementations, same honesty
discipline as the input/ backends.
"""

from __future__ import annotations

import sys


def frontmost_app_name() -> str | None:
    """The display name of the actually-frontmost application, or None if
    it can't be determined on this platform. Never guessed from history or
    assumed from "the action we just took should have worked."
    """
    if sys.platform == "darwin":
        return _frontmost_macos()
    if sys.platform == "win32":
        return _frontmost_windows()
    if sys.platform.startswith("linux"):
        return _frontmost_linux()
    return None


def _frontmost_macos() -> str | None:
    import AppKit

    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    return str(app.localizedName())


def _frontmost_windows() -> str | None:
    # UNVERIFIED ON REAL WINDOWS HARDWARE: written against documented
    # Win32 APIs, not interactively tested (no Windows machine this
    # session). CI is the only check.
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h_process = kernel32.OpenProcess(0x0410, False, pid.value)  # PROCESS_QUERY_INFORMATION | VM_READ
    if not h_process:
        return None
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        psapi = ctypes.windll.psapi  # type: ignore[attr-defined]
        if psapi.GetModuleBaseNameW(h_process, None, buf, size):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(h_process)


def _frontmost_linux() -> str | None:
    # UNVERIFIED ON REAL LINUX HARDWARE: written against the documented
    # EWMH _NET_ACTIVE_WINDOW convention, not interactively tested. Only
    # covers X11 (same scope limit as input/linux.py); Wayland has no
    # equivalent standard.
    from Xlib.display import Display

    display = Display()
    try:
        root = display.screen().root
        net_active_window = display.intern_atom("_NET_ACTIVE_WINDOW")
        prop = root.get_full_property(net_active_window, 0)
        if prop is None or not prop.value:
            return None
        window_id = prop.value[0]
        window = display.create_resource_object("window", window_id)
        net_wm_name = display.intern_atom("_NET_WM_NAME")
        name_prop = window.get_full_property(net_wm_name, 0)
        if name_prop is None:
            return None
        return bytes(name_prop.value).decode("utf-8", errors="replace")
    finally:
        display.close()


class FocusMismatchError(RuntimeError):
    """Raised when the frontmost app doesn't match what the caller
    expected, instead of sending input blind into whatever has focus.
    """


def require_frontmost(expected_substring: str) -> None:
    """Raise FocusMismatchError unless the frontmost app's name contains
    `expected_substring` (case-insensitive). This is the direct fix for
    this session's repeated "typed into the wrong window" failures: call
    it before type/key when the caller knows what should be focused.
    """
    actual = frontmost_app_name()
    if actual is None:
        raise FocusMismatchError(f"could not determine the frontmost app to verify it contains {expected_substring!r}")
    if expected_substring.lower() not in actual.lower():
        raise FocusMismatchError(f"expected frontmost app containing {expected_substring!r}, got {actual!r}")
