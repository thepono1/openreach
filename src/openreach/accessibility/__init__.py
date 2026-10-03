"""Accessibility-tree grounding: the row-1 gap from GAP_ANALYSIS.md. Reads
the OS's real accessibility tree (roles, labels, exact bounds) instead of
guessing from a screenshot, and invokes elements semantically (AXPress)
instead of coordinate-clicking where possible.

Only macOS is implemented so far; Windows (UI Automation) and Linux
(AT-SPI2) are documented extension points, not blockers to shipping.
"""

from __future__ import annotations

import sys


def get_accessibility_backend():
    """Return the native accessibility backend for this platform, or None."""
    if sys.platform == "darwin":
        from openreach.accessibility import macos

        return macos
    return None
