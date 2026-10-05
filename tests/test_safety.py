from __future__ import annotations

import pytest

from openreach.safety import is_destructive_key


@pytest.mark.parametrize(
    "combo",
    ["cmd+q", "CMD+Q", "cmd + q", "alt+f4", "ctrl+alt+delete", "win+l", "cmd+shift+q"],
)
def test_known_destructive_combos_are_flagged(combo: str) -> None:
    assert is_destructive_key(combo)


@pytest.mark.parametrize("combo", ["cmd+c", "cmd+v", "shift", "a", "ctrl+a", "cmd+s"])
def test_ordinary_combos_are_not_flagged(combo: str) -> None:
    assert not is_destructive_key(combo)


def test_combo_order_does_not_matter() -> None:
    assert is_destructive_key("q+cmd") == is_destructive_key("cmd+q")


# --- bypass regressions: aliases and extra held modifiers still quit/lock ----
# Found by probing the guard: exact-set matching let `command+q`, `meta+q`,
# `control+cmd+q` and `cmd+alt+q` through. Holding extra keys does not stop
# the OS combo from firing, so any superset of a destructive combo is blocked.


@pytest.mark.parametrize(
    "combo",
    [
        "command+q",
        "Command+Q",
        "meta+q",
        "cmd+alt+q",
        "cmd+shift+alt+q",
        "control+cmd+q",
        "super+l",
        "alt+shift+f4",
        "ctrl+alt+shift+delete",
    ],
)
def test_destructive_guard_blocks_aliases_and_supersets(combo: str) -> None:
    assert is_destructive_key(combo) is True


@pytest.mark.parametrize("combo", ["cmd+c", "ctrl+c", "q", "f4", "cmd+shift+s"])
def test_destructive_guard_does_not_overblock(combo: str) -> None:
    assert is_destructive_key(combo) is False
