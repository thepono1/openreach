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
    if sys.platform in ("darwin", "win32") or sys.platform.startswith("linux"):
        assert name is not None
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
