"""The tool-call contract: action names and params, matching Anthropic's
computer-use schema so openreach is a drop-in backend for any harness
already speaking it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ActionName(str, Enum):
    SCREENSHOT = "screenshot"
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    MIDDLE_CLICK = "middle_click"
    DOUBLE_CLICK = "double_click"
    TRIPLE_CLICK = "triple_click"
    MOUSE_MOVE = "mouse_move"
    LEFT_CLICK_DRAG = "left_click_drag"
    SCROLL = "scroll"
    TYPE = "type"
    KEY = "key"
    CURSOR_POSITION = "cursor_position"
    WAIT = "wait"


@dataclass
class Action:
    """One tool call. `coordinate` and `text` follow Anthropic's computer-use
    schema: coordinate is (x, y) in screenshot-pixel space, text is either
    literal text to type (for TYPE) or a key/chord name (for KEY, e.g. "cmd+c").
    """

    name: ActionName
    coordinate: tuple[int, int] | None = None
    start_coordinate: tuple[int, int] | None = None
    text: str | None = None
    scroll_direction: str | None = None
    scroll_amount: int | None = None
    duration: float | None = None


@dataclass
class ActionResult:
    """What a backend returns for one action. `image` is PNG bytes for
    SCREENSHOT; `position` is (x, y) for CURSOR_POSITION; `error` is set and
    everything else is None on failure, never raise across the schema boundary
    so any harness gets a uniform result shape.
    """

    ok: bool
    image: bytes | None = None
    position: tuple[int, int] | None = None
    error: str | None = None
    detail: dict = field(default_factory=dict)
