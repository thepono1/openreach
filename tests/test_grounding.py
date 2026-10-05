"""Grounding tests run real tesseract OCR against synthetic images we draw
ourselves (deterministic content, not whatever happens to be on a CI
runner's real screen) so a pass means the OCR pipeline genuinely works, not
that the test got lucky with live desktop content.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from openreach.backend import Backend
from openreach.grounding import find_text, wait_for_text
from openreach.schema import ActionName


def _ocr_ready() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


requires_ocr = pytest.mark.skipif(not _ocr_ready(), reason="tesseract not installed on this runner")


def _render_text(text: str, size: tuple[int, int] = (400, 200)) -> bytes:
    img = Image.new("RGB", size, color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 80), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@requires_ocr
def test_find_text_locates_a_rendered_word() -> None:
    image = _render_text("Submit")
    result = find_text("submit", image, min_confidence=0)
    assert result.ok
    assert len(result.matches) == 1
    assert result.matches[0].coordinate[0] > 0
    assert result.matches[0].coordinate[1] > 0


@requires_ocr
def test_find_text_is_case_insensitive() -> None:
    image = _render_text("CONFIRM")
    result = find_text("confirm", image, min_confidence=0)
    assert result.ok
    assert len(result.matches) == 1


@requires_ocr
def test_find_text_returns_no_matches_for_absent_text() -> None:
    image = _render_text("Submit")
    result = find_text("zzz_not_present_zzz", image, min_confidence=0)
    assert result.ok
    assert result.matches == []


@requires_ocr
def test_find_text_two_identical_words_is_two_matches_not_one() -> None:
    img = Image.new("RGB", (500, 300), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), "Cancel", fill="black")
    draw.text((20, 200), "Cancel", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    result = find_text("cancel", buf.getvalue(), min_confidence=0)
    assert result.ok
    assert len(result.matches) == 2


def test_find_text_fails_cleanly_without_tesseract(monkeypatch) -> None:
    import openreach.grounding as grounding_module

    monkeypatch.setattr(grounding_module, "_ocr_available", lambda: (False, "simulated: tesseract missing"))
    result = find_text("anything", b"", min_confidence=0)
    assert not result.ok
    assert "tesseract" in (result.error or "").lower()


@requires_ocr
def test_wait_for_times_out_without_spinning_forever() -> None:
    result = wait_for_text("zzz_never_appears_zzz", timeout=1.0, poll_interval=0.2)
    assert not result.ok
    assert "timed out" in (result.error or "")
    assert result.elapsed >= 1.0


def test_wait_for_fails_cleanly_when_screenshot_itself_fails(monkeypatch) -> None:
    class BrokenBackend(Backend):
        def execute(self, action):
            if action.name == ActionName.SCREENSHOT:
                from openreach.schema import ActionResult

                return ActionResult(ok=False, error="simulated capture failure")
            return super().execute(action)

    result = wait_for_text("anything", timeout=1.0, backend=BrokenBackend())
    assert not result.ok
    assert "capture failure" in (result.error or "")
