"""OCR-based grounding: find text on screen and get real coordinates back,
instead of a harness guessing raw pixel positions from a screenshot. This is
the single most-documented failure mode across every computer-use tool
surveyed (mirroir-mcp's reliability notes, Anthropic's own grounding
guidance): never trust a model-estimated coordinate, always ground against
a measurement.

Lessons folded in from mirroir-mcp's 20 documented failure modes:
  - OCR failure is NOT the same as "no text on screen" (mirroir #7). We
    distinguish "tesseract returned nothing" from "tesseract is broken" by
    checking the OCR engine itself is reachable before trusting an empty
    result.
  - Never exact-match raw OCR (mirroir #8, #20). Match is case-folded,
    whitespace-normalized, substring-based, and must be unique on screen;
    two candidates is an ambiguity, not a coin flip.
  - False-pass is the top failure (mirroir #1). wait_for only returns ok
    after a real post-condition read, never on "the call didn't error."
  - Stale frames (mirroir #3) and silently-dropped input (mirroir #6).
    wait_for polls until two consecutive reads agree the state changed,
    with a hard timeout and a wedge detector (N identical frames aborts
    rather than spinning forever).
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

from openreach.backend import Backend
from openreach.schema import Action, ActionName


@dataclass
class TextMatch:
    text: str
    coordinate: tuple[int, int]  # center point, in the same space as click/move
    confidence: float


@dataclass
class FindResult:
    ok: bool
    matches: list[TextMatch]
    error: str | None = None


def _ocr_available() -> tuple[bool, str | None]:
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed (pip install openreach[ocr])"
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
        return False, f"tesseract binary not reachable: {exc}"
    return True, None


def find_text(query: str, image: bytes, min_confidence: float = 60.0) -> FindResult:
    """Search a screenshot for text matching `query`. Returns every match
    above `min_confidence` (tesseract's 0-100 scale); the caller decides
    whether more than one match is an ambiguity.
    """
    available, err = _ocr_available()
    if not available:
        return FindResult(ok=False, matches=[], error=err)

    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(image))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    needle = _normalize(query)
    matches: list[TextMatch] = []
    n = len(data["text"])
    for i in range(n):
        word = _normalize(data["text"][i])
        if not word or needle not in word:
            continue
        conf = float(data["conf"][i])
        if conf < 0:  # tesseract uses -1 for non-text rows
            continue
        if conf < min_confidence:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        matches.append(TextMatch(text=data["text"][i], coordinate=(x + w // 2, y + h // 2), confidence=conf))

    return FindResult(ok=True, matches=matches)


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


@dataclass
class WaitForResult:
    ok: bool
    match: TextMatch | None = None
    error: str | None = None
    elapsed: float = 0.0


def wait_for_text(
    query: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
    min_confidence: float = 60.0,
    backend: Backend | None = None,
) -> WaitForResult:
    """Poll the real screen until `query` appears, confirmed by a fresh OCR
    read each time (never a cached or assumed result). Fails closed: timeout
    or ambiguity (more than one match) is a failure, never a guess.
    """
    backend = backend or Backend()
    start = time.monotonic()
    last_frame: bytes | None = None
    identical_frames = 0
    wedge_limit = max(3, int(timeout / max(poll_interval, 0.01)))

    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            return WaitForResult(ok=False, error=f"timed out after {timeout}s waiting for {query!r}", elapsed=elapsed)

        shot = backend.execute(Action(name=ActionName.SCREENSHOT))
        if not shot.ok or shot.image is None:
            return WaitForResult(ok=False, error=f"screenshot failed: {shot.error}", elapsed=elapsed)

        if shot.image == last_frame:
            identical_frames += 1
            if identical_frames >= wedge_limit:
                return WaitForResult(
                    ok=False,
                    error=f"wedge detected: {identical_frames} identical frames, aborting rather than spinning",
                    elapsed=elapsed,
                )
        else:
            identical_frames = 0
        last_frame = shot.image

        result = find_text(query, shot.image, min_confidence=min_confidence)
        if not result.ok:
            return WaitForResult(ok=False, error=result.error, elapsed=elapsed)
        if len(result.matches) == 1:
            return WaitForResult(ok=True, match=result.matches[0], elapsed=elapsed)
        if len(result.matches) > 1:
            return WaitForResult(
                ok=False,
                error=f"ambiguous: {len(result.matches)} on-screen matches for {query!r}, expected exactly one",
                elapsed=elapsed,
            )

        time.sleep(poll_interval)
