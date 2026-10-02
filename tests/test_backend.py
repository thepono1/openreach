"""Smoke tests that run against the real desktop (CI uses Xvfb on Linux,
the native desktop on macOS/Windows runners). No mocking the OS calls: a
green test here means the action actually happened on a real display.
"""

from __future__ import annotations

import pyautogui
import pytest

from openreach.backend import Backend
from openreach.schema import Action, ActionName


@pytest.fixture
def backend() -> Backend:
    return Backend()


def test_screenshot_returns_valid_png(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.SCREENSHOT))
    assert result.ok
    assert result.image is not None
    assert result.image[:8] == b"\x89PNG\r\n\x1a\n"


def test_cursor_position_returns_coordinates(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.CURSOR_POSITION))
    assert result.ok
    assert result.position is not None
    x, y = result.position
    assert x >= 0 and y >= 0


def test_mouse_move_actually_moves_cursor(backend: Backend) -> None:
    width, height = pyautogui.size()
    target = (min(100, width - 1), min(100, height - 1))
    backend.execute(Action(name=ActionName.MOUSE_MOVE, coordinate=target))
    result = backend.execute(Action(name=ActionName.CURSOR_POSITION))
    assert result.position == target


def test_unsupported_action_fails_cleanly(backend: Backend) -> None:
    class FakeAction:
        name = "not_a_real_action"

    result = backend.execute(FakeAction())  # type: ignore[arg-type]
    assert not result.ok
    assert result.error is not None


def test_mouse_move_without_coordinate_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.MOUSE_MOVE))
    assert not result.ok
    assert "coordinate" in (result.error or "")


def test_type_without_text_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.TYPE))
    assert not result.ok
    assert "text" in (result.error or "")
