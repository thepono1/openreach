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

from openreach.accessibility import get_accessibility_backend
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
        if name == "click":
            p.add_argument(
                "--verify",
                action="store_true",
                help=(
                    "macOS only: read the real accessibility element at the target point before "
                    "clicking, then confirm after clicking that the same element is still what's "
                    "there (AXUIElementCopyElementAtPosition), instead of trusting the coordinate "
                    "blindly. Adds 'target' and 'verified' to the JSON output."
                ),
            )

    p = sub.add_parser("drag", help="Drag from X,Y to X,Y")
    p.add_argument("start", type=_parse_xy)
    p.add_argument("end", type=_parse_xy)

    p = sub.add_parser("scroll", help="Scroll at an optional X,Y")
    p.add_argument("direction", choices=["up", "down", "left", "right"])
    p.add_argument("--amount", type=int, default=3)
    p.add_argument("--at", type=_parse_xy, default=None)

    p = sub.add_parser("type", help="Type literal text")
    p.add_argument("text")
    p.add_argument(
        "--expect-app",
        default=None,
        help="Refuse to type unless the frontmost app's name contains this substring",
    )

    p = sub.add_parser("key", help='Press a key or chord, e.g. "cmd+c"')
    p.add_argument("keys")
    p.add_argument("--force", action="store_true", help="Allow a destructive combo (quit, lock, log out)")
    p.add_argument(
        "--expect-app",
        default=None,
        help="Refuse to send unless the frontmost app's name contains this substring",
    )

    p = sub.add_parser("wait", help="Sleep for N seconds")
    p.add_argument("seconds", type=float)

    p = sub.add_parser("find-text", help="OCR the screen for text, print every match's coordinate")
    p.add_argument("query")
    p.add_argument("--min-confidence", type=float, default=60.0)

    p = sub.add_parser("wait-for", help="Poll the real screen until text appears (or time out)")
    p.add_argument("query")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--min-confidence", type=float, default=60.0)

    p = sub.add_parser("tree", help="Dump the accessibility tree of the frontmost app")
    p.add_argument("--max-depth", type=int, default=15)
    p.add_argument("--max-nodes", type=int, default=2000)

    p = sub.add_parser("find", help="Find accessibility elements by role and/or title substring")
    p.add_argument("--role", default=None)
    p.add_argument("--title", default=None, help="Case-insensitive substring match")

    p = sub.add_parser(
        "press",
        help="Find exactly one element by role/title and invoke it directly (AXPress), no coordinate guessing",
    )
    p.add_argument("--role", default=None)
    p.add_argument("--title", default=None)

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

    if cmd in ("tree", "find", "press"):
        ax = get_accessibility_backend()
        if ax is None:
            print(json.dumps({"ok": False, "error": "no accessibility backend for this platform yet"}))
            return 1
        if not ax.is_trusted():
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "process is not Accessibility-trusted (System Settings > Privacy & Security > Accessibility)",
                    }
                )
            )
            return 1
        return _run_accessibility_command(ax, cmd, args)

    expect_app = getattr(args, "expect_app", None)
    if expect_app:
        from openreach.focus import FocusMismatchError, require_frontmost

        try:
            require_frontmost(expect_app)
        except FocusMismatchError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 1

    if cmd == "click" and getattr(args, "verify", False):
        return _run_verified_click(args, log_dir)

    # The destructive-key gate itself now lives in Backend.execute (the
    # single chokepoint every caller goes through, library or CLI), not
    # here. This keeps _build_action's force flag passed straight through.
    action = _build_action(args)
    result = Backend().execute(action)
    return _emit(result, log_dir=log_dir, action_name=cmd)


def _run_verified_click(args: argparse.Namespace, log_dir: str | None) -> int:
    """Click with before/after accessibility-tree confirmation that the
    click actually landed on the thing at that point, not a coordinate
    trusted blindly. macOS only today (no accessibility backend on the
    other OSes yet); falls back to an ordinary click elsewhere, with
    'verified: null' to make the lack of verification explicit rather
    than silently claiming success.
    """
    backend = Backend()
    x, y = args.xy if args.xy is not None else backend.execute(Action(name=ActionName.CURSOR_POSITION)).position

    ax = get_accessibility_backend()
    if ax is None:
        result = backend.execute(Action(name=ActionName.LEFT_CLICK, coordinate=(x, y)))
        payload = {"ok": result.ok, "error": result.error, "position": [x, y], "verified": None}
        if log_dir:
            _write_artifact(log_dir, "click", payload)
        print(json.dumps(payload))
        return 0 if result.ok else 1

    target = ax.element_at(x, y)
    result = backend.execute(Action(name=ActionName.LEFT_CLICK, coordinate=(x, y)))
    verified = ax.verify_click_target(x, y, target) if target is not None else False

    payload = {
        "ok": result.ok,
        "error": result.error,
        "position": [x, y],
        "target": _element_json(target) if target is not None else None,
        "verified": verified,
    }
    if log_dir:
        _write_artifact(log_dir, "click", payload)
    print(json.dumps(payload))
    return 0 if result.ok else 1


def _element_json(e) -> dict:
    return {
        "role": e.role,
        "title": e.title,
        "value": e.value,
        "position": list(e.position) if e.position else None,
        "size": list(e.size) if e.size else None,
        "center": list(e.center) if e.center else None,
        "enabled": e.enabled,
        "actions": e.actions,
    }


def _run_accessibility_command(ax, cmd: str, args: argparse.Namespace) -> int:
    if cmd == "tree":
        elements, truncated = ax.walk_tree(max_depth=args.max_depth, max_nodes=args.max_nodes)
        payload = {"ok": True, "truncated": truncated, "elements": [_element_json(e) for e in elements]}
        print(json.dumps(payload))
        return 0

    if cmd == "find":
        elements = ax.find(role=args.role, title_contains=args.title)
        payload = {"ok": True, "elements": [_element_json(e) for e in elements]}
        print(json.dumps(payload))
        return 0

    if cmd == "press":
        matches = ax.find(role=args.role, title_contains=args.title)
        if len(matches) == 0:
            print(json.dumps({"ok": False, "error": "no element matched role/title"}))
            return 1
        if len(matches) > 1:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"ambiguous: {len(matches)} elements matched; narrow --role/--title to exactly one",
                        "elements": [_element_json(e) for e in matches],
                    }
                )
            )
            return 1
        try:
            ax.press(matches[0])
        except Exception as exc:  # noqa: BLE001 - uniform result shape at the boundary
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
            return 1
        print(json.dumps({"ok": True, "pressed": _element_json(matches[0])}))
        return 0

    raise ValueError(f"unhandled accessibility command: {cmd}")


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
