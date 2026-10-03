"""Native per-OS keyboard injection, replacing pyautogui's hotkey/typewrite
for reliability. See macos.py's module docstring for why: pyautogui posts a
chord's modifier and main key as separate CGEvents with a timing gap, which
is a real, reproducible bug (confirmed live this session: cmd+a typed a
literal "a" instead of selecting all). The fix, proven in this toolchain's
own logic-mcp, is to set modifier flags directly on the key event itself.

All three major OSes have a native backend now. Only macOS has been
verified interactively this session (AXSelectedTextRange reads, direct
HID state checks); Windows and Linux were written against documented
APIs and verified only via CI (windows-latest, ubuntu-latest/Xvfb), never
watched passing by a human. See GAP_ANALYSIS.md.
"""

from __future__ import annotations

import sys


def get_native_input():
    """Return the native input backend for this platform, or None if there
    isn't one (caller should fall back to pyautogui; today that's only
    Wayland on Linux, where XTEST has no equivalent).
    """
    if sys.platform == "darwin":
        from openreach.input import macos

        return macos
    if sys.platform == "win32":
        from openreach.input import windows

        return windows
    if sys.platform.startswith("linux"):
        from openreach.input import linux

        return linux
    return None
