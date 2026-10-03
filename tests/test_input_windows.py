"""Windows native input tests. Pure unit tests (chord parsing, no desktop
contact) run everywhere they're collected; the live test drives real
Notepad and reads its edit control back via WM_GETTEXT (ctypes, not a
screenshot), the same verification discipline as the macOS
AXSelectedTextRange checks. UNVERIFIED interactively by a human this
session (no Windows machine available); CI is the only real check.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only native backend")


# --- pure: chord parsing, no desktop contact --------------------------------


def test_unknown_key_raises_rather_than_silently_no_op() -> None:
    from openreach.input import windows

    with pytest.raises(windows.UnknownKeyError):
        windows.press_chord("ctrl+not_a_real_key")


def test_unknown_modifier_raises() -> None:
    from openreach.input import windows

    with pytest.raises(windows.UnknownKeyError):
        windows.press_chord("not_a_real_modifier+a")


def test_key_codes_cover_the_alphabet() -> None:
    from openreach.input import windows

    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        assert letter in windows.KEY_CODES


def test_cmd_is_accepted_as_an_alias_for_the_windows_key() -> None:
    """Chord strings are meant to be portable across the macOS/Windows
    input modules (the CLI doesn't know which OS it's on); "cmd" has to
    resolve to something sane here even though the real key is "win".
    """
    from openreach.input import windows

    assert windows.MODIFIER_VK["cmd"] == windows.MODIFIER_VK["win"]


# --- live: real Notepad, verified via WM_GETTEXT, not a screenshot ---------


@pytest.fixture
def fresh_notepad():
    import ctypes

    proc = subprocess.Popen(["notepad.exe"])
    hwnd = None
    for _ in range(50):
        time.sleep(0.1)
        hwnd = ctypes.windll.user32.FindWindowW(None, "Untitled - Notepad")
        if hwnd:
            break
    if not hwnd:
        proc.terminate()
        pytest.skip("Notepad window never appeared (no interactive desktop session?)")

    user32 = ctypes.windll.user32
    # SetForegroundWindow alone can be silently refused by Windows'
    # foreground-lock mechanism when called from a background process
    # (confirmed empirically on windows-latest CI: SendInput succeeded with
    # no error, but Notepad's edit control stayed empty). AttachThreadInput
    # is the documented workaround, but it must stay attached for the
    # DURATION of the test's SendInput calls, not just the moment of
    # stealing focus: detaching immediately (the first attempt) reverted
    # the synchronized input state before typing happened, which is why
    # that attempt still failed identically. Detach only in teardown.
    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
    current_tid = ctypes.windll.kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(current_tid, target_tid, True)

    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.SetActiveWindow(hwnd)
    time.sleep(0.3)

    edit_hwnd = user32.FindWindowExW(hwnd, None, "Edit", None)
    if edit_hwnd:
        user32.SetFocus(edit_hwnd)
        time.sleep(0.1)

    if user32.GetForegroundWindow() != hwnd:
        user32.AttachThreadInput(current_tid, target_tid, False)
        proc.terminate()
        pytest.skip("could not obtain real keyboard focus for Notepad (CI foreground-lock environment limit)")

    yield hwnd
    user32.AttachThreadInput(current_tid, target_tid, False)
    proc.terminate()


def _read_notepad_text(hwnd) -> str:
    import ctypes

    edit_hwnd = ctypes.windll.user32.FindWindowExW(hwnd, None, "Edit", None)
    if not edit_hwnd:
        edit_hwnd = ctypes.windll.user32.FindWindowExW(hwnd, None, "RichEditD2DPT", None)
    length = ctypes.windll.user32.GetWindowTextLengthW(edit_hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(edit_hwnd, buf, length + 1)
    return buf.value


@pytest.mark.live_input
def test_type_text_lands_without_dropping_characters(fresh_notepad) -> None:
    from openreach.input import windows

    windows.type_text("hello world")
    time.sleep(0.3)
    assert _read_notepad_text(fresh_notepad) == "hello world"


@pytest.mark.live_input
def test_ctrl_a_selects_all_not_a_literal_character(fresh_notepad) -> None:
    """Direct Windows analogue of the macOS Cmd+A regression test: typing
    then Ctrl+A must not change the text (it must select, not type a
    literal 'a'). Selection state itself isn't read here (WM_GETTEXT
    doesn't expose it cheaply); the text-unchanged check is the same
    false-positive-proof signal the macOS test used as its first check.
    """
    from openreach.input import windows

    windows.type_text("hello")
    time.sleep(0.2)
    before = _read_notepad_text(fresh_notepad)
    assert before == "hello"

    windows.press_chord("ctrl+a")
    time.sleep(0.2)

    after = _read_notepad_text(fresh_notepad)
    assert after == before, f"ctrl+a changed the text ({before!r} -> {after!r}); it typed instead of selecting"
