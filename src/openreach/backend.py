"""The OS automation implementation. pyautogui plus mss works unmodified on
macOS, Windows, and Linux (X11; Wayland needs ydotool, see README) for
mouse and screenshot actions. Keyboard actions (type/key) use a native
per-OS backend where one exists (openreach.input), falling back to
pyautogui where it doesn't yet; pyautogui's own keyboard chord handling has
a confirmed reliability bug on macOS (see openreach/input/macos.py).
Accessibility-tree grounding is a later, documented extension point behind
the same Backend interface, not a blocker to shipping.
"""

from __future__ import annotations

import io
import time

import mss
import pyautogui
from PIL import Image

from openreach.input import get_native_input
from openreach.safety import is_destructive_key
from openreach.schema import Action, ActionName, ActionResult

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01

_native_input = get_native_input()


class Backend:
    """Executes one Action against the live desktop and returns an
    ActionResult. Stateless between calls; the harness owns the loop.

    The destructive-key safety gate lives HERE, not in the CLI, so every
    caller goes through it. An earlier version only checked in cli.py;
    any direct `Backend().execute(...)` call (library use, a future
    executor.py chokepoint, a test) bypassed it entirely. Fail-closed by
    construction, not by convention.
    """

    def execute(self, action: Action) -> ActionResult:
        if action.name == ActionName.KEY and action.text and is_destructive_key(action.text) and not action.force:
            return ActionResult(
                ok=False,
                error=f"refusing destructive key combo {action.text!r} without force "
                "(quit, force-quit, lock, and log-out combos are blocked by default)",
            )
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
            # monitors[0] is mss's virtual bounding box spanning every
            # connected display, in the same coordinate space pyautogui's
            # click/move calls already use. monitors[1] is only the
            # primary display: on a multi-monitor setup that silently
            # crops the screenshot to one screen while clicks still
            # address the full virtual desktop, so a point a harness
            # grounded on a secondary monitor would never appear in the
            # image it reasoned from. This is the same failure *class* as
            # the pixel-vs-click coordinate-space bug already guarded by
            # test_screenshot_pixel_space_matches_click_coordinate_space,
            # just triggered by monitor count instead of DPI scaling.
            monitor = sct.monitors[0]
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
        if _native_input is not None:
            _native_input.type_text(action.text)
        else:
            pyautogui.typewrite(action.text, interval=0.01)
        return ActionResult(ok=True)

    def _do_key(self, action: Action) -> ActionResult:
        if not action.text:
            return ActionResult(ok=False, error="key requires text")
        if _native_input is not None:
            _native_input.press_chord(action.text)
        else:
            # pyautogui's hotkey() has a real reliability bug on at least
            # macOS (modifier flags not set on the key event itself, so a
            # chord can race and misfire as a bare keypress). Used only
            # where no native backend exists yet; see GAP_ANALYSIS.md.
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
