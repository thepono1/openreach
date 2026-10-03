"""macOS accessibility-tree tests. Real AX calls against a real app
(TextEdit's Bold checkbox, the same element this module's own live
verification used this session), never mocked: a pass means AXPress
genuinely toggled a real control, confirmed by reading AXValue back.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only native backend")


def _osascript(script: str, timeout: float = 10) -> str:
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pytest.skip("no GUI session available to drive TextEdit (expected on a hosted CI runner)")
    return result.stdout.strip()


def test_is_trusted_returns_a_bool() -> None:
    from openreach.accessibility import macos

    assert isinstance(macos.is_trusted(), bool)


@pytest.fixture
def fresh_textedit_document():
    _osascript('tell application "TextEdit" to make new document')
    _osascript('tell application "TextEdit" to activate')
    time.sleep(0.6)
    frontmost = _osascript('tell application "System Events" to get name of first process whose frontmost is true')
    if frontmost != "TextEdit":
        pytest.skip(f"TextEdit did not become frontmost (got {frontmost!r}); refusing to act blind")
    yield
    _osascript('tell application "TextEdit" to close every document saving no')


@pytest.mark.live_input
def test_walk_tree_finds_real_elements_in_textedit(fresh_textedit_document) -> None:
    from openreach.accessibility import macos

    elements, _truncated = macos.walk_tree(max_depth=10, max_nodes=500)
    roles = {e.role for e in elements}
    assert "AXWindow" in roles
    assert len(elements) > 5


@pytest.mark.live_input
def test_find_locates_the_bold_checkbox(fresh_textedit_document) -> None:
    from openreach.accessibility import macos

    matches = macos.find(role="AXCheckBox", title_contains="bold")
    assert len(matches) == 1
    assert matches[0].role == "AXCheckBox"
    assert "AXPress" in matches[0].actions


@pytest.mark.live_input
def test_press_bold_checkbox_actually_toggles_its_value(fresh_textedit_document) -> None:
    """The real regression target: AXPress must produce a VERIFIED effect
    (read back AXValue), not just return without error. logic-mcp
    documented an app that ignores AXPress while reporting success; this
    test is only meaningful because it checks the value changed, not that
    press() didn't raise.
    """
    from openreach.accessibility import macos

    before = macos.find(role="AXCheckBox", title_contains="bold")[0]
    assert before.value == "0"

    macos.press(before)
    time.sleep(0.3)

    after = macos.find(role="AXCheckBox", title_contains="bold")[0]
    assert after.value == "1", "AXPress did not change the checkbox value; it may have been ignored"


@pytest.mark.live_input
def test_press_raises_when_element_has_no_press_action(fresh_textedit_document) -> None:
    from openreach.accessibility import macos

    elements, _ = macos.walk_tree(max_depth=10, max_nodes=500)
    no_press = [e for e in elements if "AXPress" not in e.actions]
    assert no_press, "expected at least one element without AXPress to test the guard"

    with pytest.raises(macos.AccessibilityError):
        macos.press(no_press[0])
