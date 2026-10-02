"""The OS automation implementation. pyautogui plus mss works unmodified on
macOS, Windows, and Linux (X11; Wayland needs ydotool, see README). Native
per-OS backends (accessibility-tree grounding, etc.) are a later, documented
extension point behind the same Backend interface, not a blocker to shipping.
"""

from __future__ import annotations

import io
import time

import mss
import pyautogui
from PIL import Image

from openreach.schema import Action, ActionName, ActionResult

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01


class Backend:
    """Executes one Action against the live desktop and returns an
    ActionResult. Stateless between calls; the harness owns the loop.
    """

    def execute(self, action: Action) -> ActionResult:
        try:
            handler = getattr(self, f"_do_{action.name.value}")
        except AttributeError:
            return ActionResult(ok=False, error=f"unsupported action: {action.name}")
        try:
            return handler(action)
        except Exception as exc:  # noqa: BLE001 - uniform result shape at the boundary
            return ActionResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    def _do_screenshot(self, action: Action) -> ActionResult:
        with mss.MSS() as sct:
            monitor = sct.monitors[1]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return ActionResult(ok=True, image=buf.getvalue())

    def _do_cursor_position(self, action: Action) -> ActionResult:
        x, y = pyautogui.position()
        return ActionResult(ok=True, position=(x, y))

    def _do_mouse_move(self, action: Action) -> ActionResult:
        x, y = _require_coordinate(action)
        pyautogui.moveTo(x, y)
        return ActionResult(ok=True, position=(x, y))

    def _do_left_click(self, action: Action) -> ActionResult:
        return self._click(action, button="left", clicks=1)

    def _do_right_click(self, action: Action) -> ActionResult:
        return self._click(action, button="right", clicks=1)

    def _do_middle_click(self, action: Action) -> ActionResult:
        return self._click(action, button="middle", clicks=1)

    def _do_double_click(self, action: Action) -> ActionResult:
        return self._click(action, button="left", clicks=2)

    def _do_triple_click(self, action: Action) -> ActionResult:
        return self._click(action, button="left", clicks=3)

    def _click(self, action: Action, button: str, clicks: int) -> ActionResult:
        if action.coordinate is not None:
            x, y = action.coordinate
            pyautogui.moveTo(x, y)
        else:
            x, y = pyautogui.position()
        pyautogui.click(x, y, clicks=clicks, interval=0.05, button=button)
        return ActionResult(ok=True, position=(x, y))

    def _do_left_click_drag(self, action: Action) -> ActionResult:
        if action.start_coordinate is not None:
            sx, sy = action.start_coordinate
            pyautogui.moveTo(sx, sy)
        x, y = _require_coordinate(action)
        pyautogui.dragTo(x, y, button="left", duration=0.2)
        return ActionResult(ok=True, position=(x, y))

    def _do_scroll(self, action: Action) -> ActionResult:
        amount = action.scroll_amount or 3
        direction = action.scroll_direction or "down"
        if action.coordinate is not None:
            pyautogui.moveTo(*action.coordinate)
        delta = amount if direction == "up" else -amount
        if direction in ("up", "down"):
            pyautogui.scroll(delta)
        else:
            pyautogui.hscroll(amount if direction == "right" else -amount)
        return ActionResult(ok=True)

    def _do_type(self, action: Action) -> ActionResult:
        if not action.text:
            return ActionResult(ok=False, error="type requires text")
        pyautogui.typewrite(action.text, interval=0.01)
        return ActionResult(ok=True)

    def _do_key(self, action: Action) -> ActionResult:
        if not action.text:
            return ActionResult(ok=False, error="key requires text")
        keys = action.text.lower().split("+")
        pyautogui.hotkey(*keys)
        return ActionResult(ok=True)

    def _do_wait(self, action: Action) -> ActionResult:
        time.sleep(action.duration or 1.0)
        return ActionResult(ok=True)


def _require_coordinate(action: Action) -> tuple[int, int]:
    if action.coordinate is None:
        raise ValueError(f"{action.name} requires coordinate")
    return action.coordinate
