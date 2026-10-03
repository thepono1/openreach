"""CLI tests. Calls main() directly against the real desktop (same as the
backend tests), capturing stdout/exit codes, no subprocess overhead but no
mocking of the OS calls either.
"""

from __future__ import annotations

import base64
import json

import pytest

from openreach.cli import main


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    code = main(argv)
    out = capsys.readouterr().out.strip()
    return code, json.loads(out)


def test_screenshot_command_prints_valid_base64_png(capsys) -> None:
    code, payload = _run(capsys, ["screenshot"])
    assert code == 0
    assert payload["ok"] is True
    png = base64.b64decode(payload["image_base64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_position_command_prints_coordinates(capsys) -> None:
    code, payload = _run(capsys, ["position"])
    assert code == 0
    assert payload["ok"] is True
    assert len(payload["position"]) == 2


@pytest.mark.live_input
def test_move_command_reports_the_requested_position(capsys) -> None:
    code, payload = _run(capsys, ["move", "150,150"])
    assert code == 0
    assert payload["position"] == [150, 150]


@pytest.mark.live_input
def test_click_without_xy_succeeds(capsys) -> None:
    code, payload = _run(capsys, ["click"])
    assert code == 0
    assert payload["ok"] is True


def test_bad_xy_format_is_a_cli_usage_error(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["click", "not-a-coordinate"])
    assert exc.value.code != 0


@pytest.mark.live_input
def test_type_command_succeeds(capsys) -> None:
    code, payload = _run(capsys, ["type", "hello"])
    assert code == 0
    assert payload["ok"] is True


def test_wait_command_actually_waits(capsys) -> None:
    import time

    start = time.monotonic()
    code, payload = _run(capsys, ["wait", "0.2"])
    elapsed = time.monotonic() - start
    assert code == 0
    assert elapsed >= 0.18


# --- safety: destructive key combos ----------------------------------------


def test_destructive_key_combo_is_refused_without_force(capsys) -> None:
    code, payload = _run(capsys, ["key", "cmd+q"])
    assert code == 1
    assert payload["ok"] is False
    assert "force" in payload["error"].lower()


def test_destructive_key_combo_proceeds_with_force(capsys, monkeypatch) -> None:
    # --force must bypass the safety gate and reach the backend. It must
    # NOT actually fire a real cmd+q at the live desktop in a test run, so
    # the backend call is stubbed here; the thing under test is the gate
    # logic, not pyautogui's hotkey delivery (that's covered for ordinary
    # keys elsewhere, on combos with no destructive side effect).
    import openreach.cli as cli_module

    calls: list[str] = []

    class StubBackend:
        def execute(self, action):  # noqa: ANN001
            calls.append(action.text)
            from openreach.schema import ActionResult

            return ActionResult(ok=True)

    monkeypatch.setattr(cli_module, "Backend", StubBackend)
    code, payload = _run(capsys, ["key", "cmd+q", "--force"])
    assert code == 0
    assert payload["ok"] is True
    assert calls == ["cmd+q"]


@pytest.mark.live_input
def test_non_destructive_key_is_not_blocked(capsys) -> None:
    code, payload = _run(capsys, ["key", "shift"])
    assert code == 0
    assert payload["ok"] is True


# --- artifact logging (--log-dir) ------------------------------------------


def test_log_dir_writes_an_artifact_file(capsys, tmp_path) -> None:
    log_dir = tmp_path / "artifacts"
    code, _ = _run(capsys, ["--log-dir", str(log_dir), "position"])
    assert code == 0
    files = list(log_dir.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text())
    assert record["action"] == "position"
    assert record["ok"] is True


# --- find-text / wait-for ---------------------------------------------------


def test_find_text_command_runs_and_returns_json(capsys) -> None:
    code, payload = _run(capsys, ["find-text", "zzz_unlikely_to_exist_on_screen_zzz"])
    assert "ok" in payload
    assert "matches" in payload
    assert payload["matches"] == []


def test_wait_for_times_out_cleanly_on_text_that_will_never_appear(capsys) -> None:
    code, payload = _run(capsys, ["wait-for", "zzz_unlikely_to_exist_on_screen_zzz", "--timeout", "1.5"])
    assert code == 1
    assert payload["ok"] is False
    assert "error" in payload


# --- accessibility: tree / find / press -------------------------------------


def test_find_command_runs_and_returns_json(capsys) -> None:
    import sys

    code, payload = _run(capsys, ["find", "--role", "AXWindow"])
    assert "ok" in payload
    if sys.platform != "darwin":
        assert payload["ok"] is False
        assert "accessibility backend" in payload["error"]
    else:
        assert payload["ok"] is True
        assert "elements" in payload


def test_press_with_no_match_fails_cleanly(capsys) -> None:
    import sys

    code, payload = _run(capsys, ["press", "--title", "zzz_definitely_not_a_real_element_zzz"])
    assert code == 1
    assert payload["ok"] is False
    if sys.platform == "darwin":
        assert "no element matched" in payload["error"]
