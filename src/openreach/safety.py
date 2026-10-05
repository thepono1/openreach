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


# Spelling variants of the same physical key. Without this, `command+q` or
# `control+cmd+q` reach the OS as a real quit while the guard sees no match.
_KEY_ALIASES: dict[str, str] = {
    "command": "cmd",
    "meta": "cmd",
    "super": "win",
    "control": "ctrl",
    "option": "alt",
    "opt": "alt",
    "del": "delete",
}


def is_destructive_key(text: str) -> bool:
    """True if the chord contains a destructive combo. Matching is by subset:
    holding extra keys does not stop the OS combo from firing, so `cmd+alt+q`
    still quits. Fail-closed: when in doubt, block.
    """
    parts = frozenset(_KEY_ALIASES.get(p.strip(), p.strip()) for p in text.lower().split("+") if p.strip())
    return any(combo <= parts for combo in DESTRUCTIVE_KEY_COMBOS)


class DestructiveActionBlocked(Exception):
    """Raised when a destructive key combo is attempted without --force."""
