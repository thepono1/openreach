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
