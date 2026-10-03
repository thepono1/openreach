"""macOS accessibility-tree backend via AXUIElement (ApplicationServices).

This is the row-1 fix from GAP_ANALYSIS.md: instead of OCR-guessing where a
button is, read the real tree: role ("AXButton"), label, exact bounds, and
invoke it directly with AXPress rather than a coordinate click. Icon-only
buttons with no OCR-readable text become findable; stale/scaled coordinates
stop being a risk because the bounds come from the OS, not a screenshot.

Ported fresh for openreach (not copied from autopilot, which is
proprietary-licensed; see Jordan's explicit decision this session) using
the same AXUIElement APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import ApplicationServices as AX
import Quartz

# A tree walk can explode on a complex app (Chrome, Xcode); cap it so a find
# call can't hang or return an unusable firehose.
DEFAULT_MAX_DEPTH = 15
DEFAULT_MAX_NODES = 2000
MESSAGING_TIMEOUT_S = 1.0  # a hung/beachballing app shouldn't hang the caller


@dataclass
class AXElement:
    role: str
    title: str
    value: str
    position: tuple[int, int] | None
    size: tuple[int, int] | None
    enabled: bool
    actions: list[str] = field(default_factory=list)
    _ref: object = field(default=None, repr=False, compare=False)

    @property
    def center(self) -> tuple[int, int] | None:
        if self.position is None or self.size is None:
            return None
        x, y = self.position
        w, h = self.size
        return (int(x + w / 2), int(y + h / 2))


class AccessibilityError(RuntimeError):
    """Raised on a real AX failure (not trusted, element gone, action
    refused), never silently swallowed into an empty result.
    """


def is_trusted() -> bool:
    return bool(AX.AXIsProcessTrusted())


def _get_attr(ref, attr: str):
    err, value = AX.AXUIElementCopyAttributeValue(ref, attr, None)
    if err != 0:
        return None
    return value


def _element_from_ref(ref) -> AXElement:
    role = _get_attr(ref, AX.kAXRoleAttribute) or ""
    title = _get_attr(ref, AX.kAXTitleAttribute) or _get_attr(ref, AX.kAXDescriptionAttribute) or ""
    value = _get_attr(ref, AX.kAXValueAttribute)
    value = str(value) if value is not None else ""
    enabled = _get_attr(ref, AX.kAXEnabledAttribute)
    enabled = bool(enabled) if enabled is not None else True

    position = None
    pos_val = _get_attr(ref, AX.kAXPositionAttribute)
    if pos_val is not None:
        ok, point = AX.AXValueGetValue(pos_val, AX.kAXValueCGPointType, None)
        if ok:
            position = (int(point.x), int(point.y))

    size = None
    size_val = _get_attr(ref, AX.kAXSizeAttribute)
    if size_val is not None:
        ok, sz = AX.AXValueGetValue(size_val, AX.kAXValueCGSizeType, None)
        if ok:
            size = (int(sz.width), int(sz.height))

    err, action_names = AX.AXUIElementCopyActionNames(ref, None)
    actions = list(action_names) if err == 0 and action_names else []

    return AXElement(
        role=str(role),
        title=str(title),
        value=value,
        position=position,
        size=size,
        enabled=enabled,
        actions=actions,
        _ref=ref,
    )


def frontmost_app_element():
    """The AXUIElement for the frontmost application, or None if there
    isn't one (e.g. only the desktop is focused).
    """
    workspace = _frontmost_pid()
    if workspace is None:
        return None
    return AX.AXUIElementCreateApplication(workspace)


def _frontmost_pid() -> int | None:
    import AppKit

    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    return app.processIdentifier()


def walk_tree(
    root=None, max_depth: int = DEFAULT_MAX_DEPTH, max_nodes: int = DEFAULT_MAX_NODES
) -> tuple[list[AXElement], bool]:
    """Walk the tree from `root` (defaults to the frontmost app). Returns
    (elements, truncated) so a caller knows whether max_nodes cut it short
    rather than silently getting a partial, unmarked result.
    """
    if root is None:
        root = frontmost_app_element()
    if root is None:
        return [], False

    AX.AXUIElementSetMessagingTimeout(root, MESSAGING_TIMEOUT_S)

    out: list[AXElement] = []
    truncated = False
    stack = [(root, 0)]
    while stack:
        ref, depth = stack.pop()
        if len(out) >= max_nodes:
            truncated = True
            break
        out.append(_element_from_ref(ref))
        if depth >= max_depth:
            continue
        children = _get_attr(ref, AX.kAXChildrenAttribute) or []
        for child in reversed(children):
            stack.append((child, depth + 1))
    return out, truncated


def find(
    role: str | None = None,
    title_contains: str | None = None,
    root=None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> list[AXElement]:
    """Find elements matching role and/or a case-insensitive title
    substring. Never exact-matches title (mirroir lesson #8): this is a
    containment, case-folded match, same discipline as grounding.py's OCR
    find_text.
    """
    elements, _truncated = walk_tree(root, max_depth=max_depth, max_nodes=max_nodes)
    needle = title_contains.lower() if title_contains else None
    results = []
    for el in elements:
        if role is not None and el.role != role:
            continue
        if needle is not None and needle not in el.title.lower():
            continue
        results.append(el)
    return results


def press(element: AXElement) -> None:
    """Invoke AXPress on an element directly (no coordinate, no click).
    Raises if the element doesn't support AXPress or the action is refused
    at the OS level, rather than reporting success for a no-op (this is
    the exact failure mode logic-mcp documented for Logic Pro: an app can
    silently ignore AXPress even when frontmost).
    """
    if "AXPress" not in element.actions:
        raise AccessibilityError(f"element {element.role!r}/{element.title!r} has no AXPress action")
    err = AX.AXUIElementPerformAction(element._ref, "AXPress")
    if err != 0:
        raise AccessibilityError(f"AXPress refused (AXError {err}) on {element.role!r}/{element.title!r}")


def set_value(element: AXElement, value: str) -> None:
    """Set AXValue directly, bypassing synthetic key events entirely.
    Raises if the attribute isn't settable rather than silently no-op'ing.
    """
    settable_err, settable = AX.AXUIElementIsAttributeSettable(element._ref, AX.kAXValueAttribute, None)
    if settable_err != 0 or not settable:
        raise AccessibilityError(f"AXValue is not settable on {element.role!r}/{element.title!r}")
    err = AX.AXUIElementSetAttributeValue(element._ref, AX.kAXValueAttribute, value)
    if err != 0:
        raise AccessibilityError(f"AXUIElementSetAttributeValue refused (AXError {err})")


def element_at(x: int, y: int) -> AXElement | None:
    """What is actually under this screen point, read from the OS, not
    guessed. This is the cursor-accuracy primitive: a harness can click
    (x, y), then call this to confirm the thing it hit is the thing it
    meant to hit, instead of trusting the coordinate blindly. Uses the
    system-wide element, so it works across app boundaries (unlike find(),
    which is scoped to one app's tree).

    Returns None if there's nothing there (e.g. empty desktop) or the
    system call itself fails; the two aren't distinguished because a
    harness checking "what did I actually hit" treats both as "nothing
    identifiable", not as different error conditions worth separate
    handling.
    """
    system_wide = AX.AXUIElementCreateSystemWide()
    err, ref = AX.AXUIElementCopyElementAtPosition(system_wide, float(x), float(y), None)
    if err != 0 or ref is None:
        return None
    return _element_from_ref(ref)


def verify_click_target(x: int, y: int, expected: AXElement, tolerance_px: int = 2) -> bool:
    """After clicking (x, y) meant to hit `expected`, confirm it actually
    did: read what's really at that point now and compare role, title, and
    that the point still falls within the expected element's own bounds
    (within `tolerance_px`, to absorb integer rounding, not real drift).
    False means the click likely landed on the wrong thing, for example
    because the UI shifted between grounding and clicking, exactly the
    stale-coordinate failure class a pure screenshot/OCR approach can't
    detect at all.
    """
    actual = element_at(x, y)
    if actual is None:
        return False
    if actual.role == expected.role and actual.title == expected.title:
        return True
    if expected.position is not None and expected.size is not None:
        ex, ey = expected.position
        ew, eh = expected.size
        return (ex - tolerance_px) <= x <= (ex + ew + tolerance_px) and (ey - tolerance_px) <= y <= (
            ey + eh + tolerance_px
        )
    return False
