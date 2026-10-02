"""Fail-closed guard for destructive actions, ported from the same posture
mirroir-mcp and autopilot both use: refuse by default, require an explicit
flag to override, never infer consent from context.
"""

from __future__ import annotations

# System-level combos that quit apps, force-restart, wipe, or otherwise act
# outside the target application's own undo history. Lowercase, order-
# independent (checked as a frozenset of parts).
DESTRUCTIVE_KEY_COMBOS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"cmd", "q"}),  # quit app (macOS)
        frozenset({"cmd", "alt", "esc"}),  # force quit dialog (macOS)
        frozenset({"cmd", "shift", "q"}),  # log out (macOS)
        frozenset({"alt", "f4"}),  # close window / quit (Windows/Linux)
        frozenset({"ctrl", "alt", "delete"}),  # security screen (Windows)
        frozenset({"ctrl", "alt", "f4"}),
        frozenset({"cmd", "ctrl", "q"}),  # lock screen (macOS)
        frozenset({"win", "l"}),  # lock screen (Windows)
    }
)


def is_destructive_key(text: str) -> bool:
    parts = frozenset(p.strip() for p in text.lower().split("+"))
    return parts in DESTRUCTIVE_KEY_COMBOS


class DestructiveActionBlocked(Exception):
    """Raised when a destructive key combo is attempted without --force."""
