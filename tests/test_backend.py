"""Tests run against the real desktop (CI uses Xvfb on Linux, the native
desktop on macOS/Windows runners). No mocking the OS calls: a green test
here means the action actually happened on a real display.
"""

from __future__ import annotations

import time

import pyautogui
import pytest

from openreach.backend import Backend
from openreach.schema import Action, ActionName


@pytest.fixture
def backend() -> Backend:
    return Backend()


@pytest.fixture
def screen_size() -> tuple[int, int]:
    return pyautogui.size()


def _safe_point(screen_size: tuple[int, int], x: int, y: int) -> tuple[int, int]:
    width, height = screen_size
    return min(x, width - 1), min(y, height - 1)


# --- screenshot ---------------------------------------------------------


def test_screenshot_returns_valid_png(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.SCREENSHOT))
    assert result.ok
    assert result.image is not None
    assert result.image[:8] == b"\x89PNG\r\n\x1a\n"


def test_screenshot_dimensions_match_a_real_display(backend: Backend) -> None:
    import io

    from PIL import Image

    result = backend.execute(Action(name=ActionName.SCREENSHOT))
    img = Image.open(io.BytesIO(result.image))
    assert img.width > 0
    assert img.height > 0


def test_screenshot_pixel_space_matches_click_coordinate_space(
    backend: Backend, screen_size
) -> None:
    """Regression test for the failure class mirroir-mcp documented (a
    mirrored-window case where screenshot pixels and tap points differ by a
    scale factor, so a coordinate read from the image lands in the wrong
    place when clicked). If a screenshot's pixel dimensions ever diverge
    from pyautogui's coordinate space on some platform/display combo, a
    harness grounding clicks from OCR'd screenshot coordinates would
    silently misfire. This must hold for find-text/click to be safe to
    chain together.
    """
    import io

    from PIL import Image

    result = backend.execute(Action(name=ActionName.SCREENSHOT))
    img = Image.open(io.BytesIO(result.image))
    width, height = screen_size
    assert (img.width, img.height) == (width, height), (
        "screenshot pixel size does not match pyautogui's click coordinate "
        "space; coordinates from find-text would land in the wrong place"
    )


def test_two_screenshots_in_a_row_both_succeed(backend: Backend) -> None:
    first = backend.execute(Action(name=ActionName.SCREENSHOT))
    second = backend.execute(Action(name=ActionName.SCREENSHOT))
    assert first.ok and second.ok
    assert first.image != b""
    assert second.image != b""


# --- cursor position / move --------------------------------------------


def test_cursor_position_returns_coordinates(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.CURSOR_POSITION))
    assert result.ok
    assert result.position is not None
    x, y = result.position
    assert x >= 0 and y >= 0


def test_mouse_move_actually_moves_cursor(backend: Backend, screen_size) -> None:
    target = _safe_point(screen_size, 100, 100)
    backend.execute(Action(name=ActionName.MOUSE_MOVE, coordinate=target))
    result = backend.execute(Action(name=ActionName.CURSOR_POSITION))
    assert result.position == target


def test_mouse_move_to_a_different_point_actually_changes_position(
    backend: Backend, screen_size
) -> None:
    a = _safe_point(screen_size, 50, 50)
    b = _safe_point(screen_size, 250, 150)
    backend.execute(Action(name=ActionName.MOUSE_MOVE, coordinate=a))
    pos_a = backend.execute(Action(name=ActionName.CURSOR_POSITION)).position
    backend.execute(Action(name=ActionName.MOUSE_MOVE, coordinate=b))
    pos_b = backend.execute(Action(name=ActionName.CURSOR_POSITION)).position
    assert pos_a != pos_b
    assert pos_b == b


def test_mouse_move_without_coordinate_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.MOUSE_MOVE))
    assert not result.ok
    assert "coordinate" in (result.error or "")


# --- clicks --------------------------------------------------------------


@pytest.mark.parametrize(
    "action_name",
    [
        ActionName.LEFT_CLICK,
        ActionName.RIGHT_CLICK,
        ActionName.MIDDLE_CLICK,
        ActionName.DOUBLE_CLICK,
        ActionName.TRIPLE_CLICK,
    ],
)
def test_click_variants_move_to_target_and_report_position(
    backend: Backend, screen_size, action_name
) -> None:
    target = _safe_point(screen_size, 120, 120)
    result = backend.execute(Action(name=action_name, coordinate=target))
    assert result.ok
    assert result.position == target


def test_click_without_coordinate_clicks_at_current_position(
    backend: Backend, screen_size
) -> None:
    here = _safe_point(screen_size, 80, 80)
    backend.execute(Action(name=ActionName.MOUSE_MOVE, coordinate=here))
    result = backend.execute(Action(name=ActionName.LEFT_CLICK))
    assert result.ok
    assert result.position == here


# --- drag ------------------------------------------------------------------


def test_left_click_drag_ends_at_the_target_coordinate(
    backend: Backend, screen_size
) -> None:
    start = _safe_point(screen_size, 60, 60)
    end = _safe_point(screen_size, 200, 180)
    result = backend.execute(
        Action(name=ActionName.LEFT_CLICK_DRAG, start_coordinate=start, coordinate=end)
    )
    assert result.ok
    assert result.position == end
    final = backend.execute(Action(name=ActionName.CURSOR_POSITION)).position
    assert final == end


def test_drag_without_target_coordinate_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.LEFT_CLICK_DRAG, start_coordinate=(10, 10)))
    assert not result.ok
    assert "coordinate" in (result.error or "")


# --- scroll ------------------------------------------------------------------


@pytest.mark.parametrize("direction", ["up", "down", "left", "right"])
def test_scroll_in_every_direction_succeeds(backend: Backend, direction) -> None:
    result = backend.execute(
        Action(name=ActionName.SCROLL, scroll_direction=direction, scroll_amount=2)
    )
    assert result.ok


def test_scroll_defaults_to_down_with_no_args(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.SCROLL))
    assert result.ok


# --- type / key --------------------------------------------------------------


def test_type_without_text_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.TYPE))
    assert not result.ok
    assert "text" in (result.error or "")


def test_type_empty_string_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.TYPE, text=""))
    assert not result.ok


def test_key_without_text_fails_cleanly(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.KEY))
    assert not result.ok
    assert "text" in (result.error or "")


def test_key_single_key_succeeds(backend: Backend) -> None:
    result = backend.execute(Action(name=ActionName.KEY, text="shift"))
    assert result.ok


# --- wait --------------------------------------------------------------------


def test_wait_actually_sleeps_for_roughly_the_requested_duration(backend: Backend) -> None:
    start = time.monotonic()
    result = backend.execute(Action(name=ActionName.WAIT, duration=0.3))
    elapsed = time.monotonic() - start
    assert result.ok
    assert elapsed >= 0.28


def test_wait_with_no_duration_defaults_to_one_second(backend: Backend) -> None:
    start = time.monotonic()
    backend.execute(Action(name=ActionName.WAIT))
    elapsed = time.monotonic() - start
    assert elapsed >= 0.9


# --- error handling at the boundary ------------------------------------------


def test_unsupported_action_fails_cleanly(backend: Backend) -> None:
    class FakeAction:
        name = "not_a_real_action"

    result = backend.execute(FakeAction())  # type: ignore[arg-type]
    assert not result.ok
    assert result.error is not None


def test_every_result_is_a_result_object_never_a_raised_exception(backend: Backend) -> None:
    for name in ActionName:
        result = backend.execute(Action(name=name))
        assert result.ok in (True, False)
