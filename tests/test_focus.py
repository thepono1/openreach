"""Focus verification tests. The direct fix for this session's repeated
"typed into the wrong window" failures: require_frontmost must refuse
before any input is sent when the frontmost app doesn't match, verified
against the real frontmost app on this machine, not mocked.
"""

from __future__ import annotations

import sys

import pytest

from openreach.focus import FocusMismatchError, frontmost_app_name, require_frontmost


def test_frontmost_app_name_returns_something_real() -> None:
    name = frontmost_app_name()
    if sys.platform in ("darwin", "win32"):
        assert name is not None
        assert len(name) > 0
    elif sys.platform.startswith("linux"):
        # _NET_ACTIVE_WINDOW is a window-manager convention, not a core X11
        # feature. Xvfb (what CI's ubuntu-latest leg uses) runs no window
        # manager, so None here is the correct, honest answer, not a bug:
        # confirmed live via CI, not assumed. A real desktop with a WM
        # should return a real name; this test only enforces "didn't
        # crash and returned a sane type" when that's true.
        if name is not None:
            assert len(name) > 0


def test_require_frontmost_raises_for_an_app_that_is_not_focused() -> None:
    with pytest.raises(FocusMismatchError):
        require_frontmost("zzz_definitely_not_the_frontmost_app_zzz")


def test_require_frontmost_passes_for_the_real_frontmost_app() -> None:
    name = frontmost_app_name()
    if name is None:
        pytest.skip("frontmost_app_name() returned None on this platform")
    # A substring of the real name must pass; using the full name avoids
    # false negatives from partial-word matches.
    require_frontmost(name)


def test_require_frontmost_is_case_insensitive() -> None:
    name = frontmost_app_name()
    if name is None:
        pytest.skip("frontmost_app_name() returned None on this platform")
    require_frontmost(name.upper())
    require_frontmost(name.lower())


def test_settled_check_waits_for_window_switch(monkeypatch) -> None:
    from openreach import focus

    answers = iter(["Finder", "Finder", "TextEdit"])
    monkeypatch.setattr(focus, "frontmost_app_name", lambda: next(answers))
    import time

    monkeypatch.setattr(time, "sleep", lambda s: None)
    focus.require_frontmost_settled("textedit", timeout=5.0, interval=0.01)


def test_settled_check_still_refuses_after_timeout(monkeypatch) -> None:
    import pytest

    from openreach import focus

    monkeypatch.setattr(focus, "frontmost_app_name", lambda: "Finder")
    with pytest.raises(focus.FocusMismatchError, match="still not frontmost"):
        focus.require_frontmost_settled("textedit", timeout=0.05, interval=0.01)
