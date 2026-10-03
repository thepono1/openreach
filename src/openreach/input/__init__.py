"""Native per-OS keyboard injection, replacing pyautogui's hotkey/typewrite
for reliability. See macos.py's module docstring for why: pyautogui posts a
chord's modifier and main key as separate CGEvents with a timing gap, which
is a real, reproducible bug (confirmed live this session: cmd+a typed a
literal "a" instead of selecting all). The fix, proven in this toolchain's
own logic-mcp, is to set modifier flags directly on the key event itself.

Windows and Linux backends are not implemented yet (see GAP_ANALYSIS.md);
callers fall back to pyautogui there today. This module is additive: the
existing Backend keeps working exactly as before on platforms without a
native backend.
"""

from __future__ import annotations

import sys


def get_native_input():
    """Return the native input backend for this platform, or None if there
    isn't one yet (caller should fall back to pyautogui).
    """
    if sys.platform == "darwin":
        from openreach.input import macos

        return macos
    return None
