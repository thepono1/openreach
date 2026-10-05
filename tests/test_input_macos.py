"""macOS native input tests. Pure unit tests (chord parsing, no desktop
contact) plus one real live-desktop regression test for the exact bug
found and fixed this session: pyautogui's hotkey() typed a literal "a"
instead of selecting all, confirmed by reading AXSelectedTextRange via
System Events, never by eyeballing a screenshot.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only native backend")


def _osascript(script: str, timeout: float = 10) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout, check=False)
    return result.stdout.strip()


# --- pure: chord parsing, no desktop contact --------------------------------


def test_unknown_key_raises_rather_than_silently_no_op() -> None:
    from openreach.input import macos

    with pytest.raises(macos.UnknownKeyError):
        macos.press_chord("cmd+not_a_real_key")


def test_unknown_modifier_raises() -> None:
    from openreach.input import macos

    with pytest.raises(macos.UnknownKeyError):
        macos.press_chord("not_a_real_modifier+a")


def test_key_codes_cover_the_alphabet() -> None:
    from openreach.input import macos

    for letter in "abcdefghijklmnopqrstuvwxyz":
        assert letter in macos.KEY_CODES


@pytest.mark.live_input
def test_a_stuck_modifier_is_cleared_before_typing() -> None:
    """Regression test for the actual bug found live this session: a
    leftover pyautogui.hotkey() call left Cmd stuck held at the HID level,
    system-wide, well after it returned, silently corrupting every
    subsequent keystroke into a Cmd-chord. Simulates that stuck state on
    purpose, then confirms type_text's defensive clear actually clears it.
    """
    # Simulate the stuck state: post a Cmd keydown with no matching keyup,
    # exactly what an interrupted pyautogui.hotkey() call left behind.
    import time

    import Quartz

    from openreach.input import macos

    stuck = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
    Quartz.CGEventSetType(stuck, Quartz.kCGEventFlagsChanged)
    Quartz.CGEventSetFlags(stuck, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, stuck)
    time.sleep(0.05)  # let the OS process the simulated event before reading state back

    flags_before = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
    assert flags_before & Quartz.kCGEventFlagMaskCommand, "test setup failed to simulate a stuck Cmd"

    cleared = macos.clear_stuck_modifiers()
    assert cleared is True

    flags_after = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
    assert not (flags_after & Quartz.kCGEventFlagMaskCommand), "clear_stuck_modifiers did not release Cmd"


# --- live: the actual regression, verified via Accessibility, not pixels ---


@pytest.fixture
def fresh_textedit_document():
    # Hosted CI runners (confirmed on GitHub's macos-latest) have no
    # logged-in GUI session capable of launching and driving TextEdit via
    # AppleScript/Accessibility: the call hangs rather than erroring, which
    # is exactly the open risk the architecture plan flagged as unverified.
    # Skip cleanly here instead of hanging the whole suite; this is an
    # environment limitation, not evidence the feature is broken (it's
    # proven working against a real desktop in test_input_macos.py's own
    # manual verification this session, and the pure chord-parsing tests
    # above still run everywhere).
    try:
        _osascript('tell application "TextEdit" to make new document', timeout=5)
    except subprocess.TimeoutExpired:
        pytest.skip("no GUI session available to drive TextEdit (expected on a hosted CI runner)")
    _osascript('tell application "TextEdit" to activate')
    import time

    time.sleep(0.6)
    frontmost = _osascript('tell application "System Events" to get name of first process whose frontmost is true')
    assert frontmost == "TextEdit", f"TextEdit did not become frontmost (got {frontmost!r}); refusing to type blind"
    yield
    _osascript('tell application "TextEdit" to close every document saving no')


@pytest.mark.live_input
def test_type_text_lands_without_dropping_characters(fresh_textedit_document) -> None:
    from openreach.input import macos

    macos.type_text("hello world")
    value = _osascript(
        'tell application "System Events" to tell process "TextEdit" '
        "to return value of text area 1 of scroll area 1 of window 1"
    )
    # TextEdit autocapitalizes the first letter; the content must be intact,
    # not truncated the way pyautogui.typewrite dropped characters earlier.
    assert value.lower() == "hello world"


@pytest.mark.live_input
def test_cmd_a_selects_all_not_a_literal_character(fresh_textedit_document) -> None:
    """Direct regression test for today's live bug: pyautogui.hotkey('cmd',
    'a') typed a literal "a" (text became "...a") instead of selecting all.
    Verified two ways: the text must NOT have grown, and the real selection
    range must cover the whole string.
    """
    from openreach.input import macos

    macos.type_text("hello")
    before = _osascript(
        'tell application "System Events" to tell process "TextEdit" '
        "to return value of text area 1 of scroll area 1 of window 1"
    )
    assert before.lower() == "hello"

    macos.press_chord("cmd+a")

    after = _osascript(
        'tell application "System Events" to tell process "TextEdit" '
        "to return value of text area 1 of scroll area 1 of window 1"
    )
    assert after == before, f"cmd+a changed the text ({before!r} -> {after!r}); it typed instead of selecting"

    selection_range = _osascript(
        'tell application "System Events" to tell process "TextEdit" to tell window 1 '
        'to return value of attribute "AXSelectedTextRange" of text area 1 of scroll area 1'
    )
    # "hello" is 5 characters; a real select-all reports a selection length of 5.
    assert selection_range.endswith(", 5"), f"selection did not cover the full string: {selection_range!r}"


@pytest.mark.live_input
def test_chord_leaves_no_modifier_stuck_at_os_level() -> None:
    """A chord must not leave Cmd/Shift/Option/Control held system-wide after it
    returns. Read the real HID modifier state after, not the return value.
    """
    import subprocess

    import Quartz

    from openreach.input import macos

    subprocess.run(["osascript", "-e", 'tell application "TextEdit" to make new document'], check=False)
    subprocess.run(["osascript", "-e", 'tell application "TextEdit" to activate'], check=False)
    try:
        macos.press_chord("cmd+a")
        flags = Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState)
        held = flags & (
            Quartz.kCGEventFlagMaskCommand
            | Quartz.kCGEventFlagMaskShift
            | Quartz.kCGEventFlagMaskAlternate
            | Quartz.kCGEventFlagMaskControl
        )
        assert held == 0, f"modifier still held after chord: flags={flags:#x}"
    finally:
        subprocess.run(["osascript", "-e", 'tell application "TextEdit" to close every document saving no'], check=False)
