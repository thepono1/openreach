"""Command-line interface. Any harness (human, script, or LLM agent via
subprocess) drives the desktop through this, not an MCP server: `openreach
screenshot`, `openreach click 100 200`, `openreach type "hello"`, etc.
One verb per subcommand, JSON on stdout for machine consumption, exit code 0
on success and 1 on failure so scripts can branch without parsing text.

Safety: destructive key combos (quit, force-quit, lock, log out) are
refused unless `--force` is passed, fail-closed by default. This mirrors
the posture of mirroir-mcp's permissions gate and autopilot's safety
registry, both audited elsewhere in this toolchain.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

from openreach.backend import Backend
from openreach.grounding import find_text, wait_for_text
from openreach.schema import Action, ActionName, ActionResult


def _emit(result: ActionResult, log_dir: str | None = None, action_name: str = "") -> int:
    payload: dict = {"ok": result.ok}
    if result.position is not None:
        payload["position"] = list(result.position)
    if result.image is not None:
        payload["image_base64"] = base64.b64encode(result.image).decode("ascii")
    if result.error is not None:
        payload["error"] = result.error
    if log_dir:
        _write_artifact(log_dir, action_name, payload)
    print(json.dumps(payload))
    return 0 if result.ok else 1


def _write_artifact(log_dir: str, action_name: str, payload: dict) -> None:
    """Per-call before/after artifact logging, folded in from mirroir-mcp's
    documented lesson that per-step artifacts are the highest-leverage
    reliability investment for a solo harness (reliability.md #13).
    """
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    record = {"timestamp": stamp, "action": action_name, **payload}
    with open(path / f"{stamp}-{action_name}.json", "w") as f:
        json.dump(record, f, indent=2)


def _parse_xy(value: str) -> tuple[int, int]:
    try:
        x, y = value.split(",")
        return int(x), int(y)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected X,Y, got {value!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openreach", description=__doc__)
    parser.add_argument("--log-dir", default=None, help="Write a before/after JSON artifact per call")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("screenshot", help="Capture the primary display as PNG (base64 on stdout)")
    sub.add_parser("position", help="Print the current cursor position")

    for name in ("click", "right-click", "middle-click", "double-click", "triple-click", "move"):
        p = sub.add_parser(name, help=f"{name.replace('-', ' ').capitalize()} at X,Y")
        p.add_argument("xy", type=_parse_xy, nargs="?", help="X,Y coordinate; omit to act at the current position")

    p = sub.add_parser("drag", help="Drag from X,Y to X,Y")
    p.add_argument("start", type=_parse_xy)
    p.add_argument("end", type=_parse_xy)

    p = sub.add_parser("scroll", help="Scroll at an optional X,Y")
    p.add_argument("direction", choices=["up", "down", "left", "right"])
    p.add_argument("--amount", type=int, default=3)
    p.add_argument("--at", type=_parse_xy, default=None)

    p = sub.add_parser("type", help="Type literal text")
    p.add_argument("text")

    p = sub.add_parser("key", help='Press a key or chord, e.g. "cmd+c"')
    p.add_argument("keys")
    p.add_argument("--force", action="store_true", help="Allow a destructive combo (quit, lock, log out)")

    p = sub.add_parser("wait", help="Sleep for N seconds")
    p.add_argument("seconds", type=float)

    p = sub.add_parser("find-text", help="OCR the screen for text, print every match's coordinate")
    p.add_argument("query")
    p.add_argument("--min-confidence", type=float, default=60.0)

    p = sub.add_parser("wait-for", help="Poll the real screen until text appears (or time out)")
    p.add_argument("query")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--min-confidence", type=float, default=60.0)

    return parser


_NAME_MAP = {
    "click": ActionName.LEFT_CLICK,
    "right-click": ActionName.RIGHT_CLICK,
    "middle-click": ActionName.MIDDLE_CLICK,
    "double-click": ActionName.DOUBLE_CLICK,
    "triple-click": ActionName.TRIPLE_CLICK,
    "move": ActionName.MOUSE_MOVE,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.command
    log_dir = args.log_dir

    if cmd == "find-text":
        shot = Backend().execute(Action(name=ActionName.SCREENSHOT))
        if not shot.ok:
            print(json.dumps({"ok": False, "error": shot.error}))
            return 1
        result = find_text(args.query, shot.image, min_confidence=args.min_confidence)
        payload = {
            "ok": result.ok,
            "error": result.error,
            "matches": [
                {"text": m.text, "coordinate": list(m.coordinate), "confidence": m.confidence} for m in result.matches
            ],
        }
        print(json.dumps(payload))
        return 0 if result.ok else 1

    if cmd == "wait-for":
        result = wait_for_text(args.query, timeout=args.timeout, min_confidence=args.min_confidence)
        payload = {"ok": result.ok, "error": result.error, "elapsed": result.elapsed}
        if result.match:
            payload["match"] = {
                "text": result.match.text,
                "coordinate": list(result.match.coordinate),
                "confidence": result.match.confidence,
            }
        print(json.dumps(payload))
        return 0 if result.ok else 1

    # The destructive-key gate itself now lives in Backend.execute (the
    # single chokepoint every caller goes through, library or CLI), not
    # here. This keeps _build_action's force flag passed straight through.
    action = _build_action(args)
    result = Backend().execute(action)
    return _emit(result, log_dir=log_dir, action_name=cmd)


def _build_action(args: argparse.Namespace) -> Action:
    cmd = args.command
    if cmd == "screenshot":
        return Action(name=ActionName.SCREENSHOT)
    if cmd == "position":
        return Action(name=ActionName.CURSOR_POSITION)
    if cmd in _NAME_MAP:
        return Action(name=_NAME_MAP[cmd], coordinate=args.xy)
    if cmd == "drag":
        return Action(name=ActionName.LEFT_CLICK_DRAG, start_coordinate=args.start, coordinate=args.end)
    if cmd == "scroll":
        return Action(
            name=ActionName.SCROLL,
            scroll_direction=args.direction,
            scroll_amount=args.amount,
            coordinate=args.at,
        )
    if cmd == "type":
        return Action(name=ActionName.TYPE, text=args.text)
    if cmd == "key":
        return Action(name=ActionName.KEY, text=args.keys, force=args.force)
    if cmd == "wait":
        return Action(name=ActionName.WAIT, duration=args.seconds)
    raise ValueError(f"unhandled command: {cmd}")


if __name__ == "__main__":
    sys.exit(main())
