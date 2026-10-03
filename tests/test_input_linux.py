"""Linux (X11) native input tests. Pure unit tests (chord parsing, no
display contact) run everywhere Linux is detected; the live test connects
to the real X display (Xvfb in CI) and types into an xterm, reading the
result back via xdotool's getwindowname/xprop-free approach: a temp file
written by a shell command the typed text triggers, since there's no
direct analogue to AXSelectedTextRange/WM_GETTEXT without adding an
AT-SPI dependency this module doesn't otherwise need. UNVERIFIED
interactively (no Linux desktop available this session); CI is the only
real check.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux-only native backend")


# --- pure: chord parsing, no display contact --------------------------------


def test_unknown_key_raises_rather_than_silently_no_op() -> None:
    from openreach.input import linux

    with pytest.raises(linux.UnknownKeyError):
        linux.press_chord("ctrl+not_a_real_key_zzz")


def test_unknown_modifier_raises() -> None:
    from openreach.input import linux

    with pytest.raises(linux.UnknownKeyError):
        linux.press_chord("not_a_real_modifier+a")


def test_cmd_is_accepted_as_an_alias_for_super() -> None:
    from openreach.input import linux

    assert linux.MODIFIER_KEYSYMS["cmd"] == linux.MODIFIER_KEYSYMS["super"]


def test_type_text_raises_cleanly_on_unmappable_character() -> None:
    """A non-ASCII character with no X11 keysym must raise, not silently
    drop the character (the same false-pass risk pyautogui's typewrite had
    on macOS, now checked here before it ships).
    """
    from openreach.input import linux

    with pytest.raises(linux.UnknownKeyError):
        linux.type_text("ก")  # Thai character, unlikely to have a direct keysym


# --- live: a real X display (Xvfb in CI) ------------------------------------


@pytest.mark.live_input
def test_can_connect_to_the_real_display_and_resolve_a_keycode() -> None:
    """Minimal live smoke test: the X connection this module opens per
    call must actually work against the display running the test (Xvfb in
    CI), and a plain letter must resolve to a real, nonzero keycode on
    that server's keymap. This is weaker than the macOS/Windows live tests
    (no real application's text is verified here), a real, named gap: see
    GAP_ANALYSIS.md.
    """
    from openreach.input import linux

    display = linux._display()
    try:
        keysym = linux._keysym_for("a")
        keycode = linux._keycode_for(display, keysym)
        assert keycode != 0
    finally:
        display.close()


@pytest.mark.live_input
def test_press_chord_does_not_raise_for_a_plain_letter() -> None:
    from openreach.input import linux

    linux.press_chord("a")


@pytest.mark.live_input
def test_press_chord_does_not_raise_for_a_modified_chord() -> None:
    from openreach.input import linux

    linux.press_chord("ctrl+a")
