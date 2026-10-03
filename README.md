# openreach

Open-source, cross-OS computer-use tool for any LLM harness. Screenshot, click, type, scroll, and (on macOS) read and invoke the real accessibility tree: on macOS, Windows, or Linux, through one tool-call contract.

## Why

Anthropic's computer-use tool schema (`screenshot`, `left_click`, `type`, `key`, `scroll`, `cursor_position`, `wait`, ...) is the de facto standard any agent harness already speaks. The reference server-side implementation is closed; the OS automation underneath it doesn't need to be. openreach implements that same contract as a small, testable, MIT-licensed library any harness can call.

The deeper goal: Claude-in-Chrome's real advantage isn't vision, it's that a browser extension can read the DOM/accessibility tree directly and invoke elements semantically instead of guessing pixel coordinates. openreach brings that same approach to the whole desktop using each OS's native accessibility API, not a proprietary extension.

## Design

- `src/openreach/schema.py`: the tool-call contract (action names, params), matching Anthropic's computer-use schema.
- `src/openreach/backend.py`: pixel-level actions (screenshot via `mss`, mouse via `pyautogui`). Keyboard actions (`type`/`key`) route through a native per-OS backend when one exists, falling back to `pyautogui` otherwise; the destructive-key safety gate lives here too, so every caller (library or CLI) goes through it.
- `src/openreach/input/`: native keyboard injection per OS. `macos.py` (Quartz `CGEvent`, verified live), `windows.py` (`SendInput` via ctypes), `linux.py` (XTEST via `python-xlib`, X11 only). Why native instead of `pyautogui`'s own chord handling: `pyautogui.hotkey()` on macOS has a real, confirmed bug (modifier flags not set atomically on the key event, so a chord can race and misfire as a plain keypress). See `GAP_ANALYSIS.md`.
- `src/openreach/accessibility/`: the real accessibility tree. `macos.py` (`AXUIElement`) reads roles/titles/bounds/actions and invokes elements directly via `AXPress`, no coordinate guessing. Windows (UI Automation) and Linux (AT-SPI2) are documented, not yet built.
- `src/openreach/grounding.py`: OCR-based `find_text`/`wait_for_text` (pytesseract) as the fallback for apps with no usable accessibility tree, or on platforms without a native accessibility backend yet.
- `src/openreach/focus.py`: pre-action focus verification (`--expect-app`), refusing to send input when the frontmost app doesn't match what the caller expected.
- `src/openreach/safety.py`: fail-closed guard on destructive key combos (quit, force-quit, lock, log out).
- `src/openreach/cli.py`: the `openreach` command. Any harness drives the desktop by shelling out to it, JSON on stdout, exit code 0/1. No MCP server, no daemon.

## CLI

```
pip install -e ".[dev]"   # add [ocr] for OCR grounding

openreach screenshot                    # PNG, base64-encoded, on stdout as JSON
openreach position
openreach click 100,200
openreach double-click 100,200
openreach drag 100,200 300,400
openreach scroll down --amount 5 --at 100,200
openreach type "hello world" --expect-app "TextEdit"
openreach key "cmd+c"
openreach wait 1.5

openreach find-text "Submit" --min-confidence 70
openreach wait-for "Loading..." --timeout 10

# macOS only today:
openreach tree --max-depth 10
openreach find --role AXButton --title "Submit"
openreach press --role AXButton --title "Submit"
```

## Testing philosophy

Every claim is a test, and every live-desktop test says exactly how it was verified: a direct OS-level read-back (`AXSelectedTextRange`, `WM_GETTEXT`, `CGEventSourceFlagsState`), never a screenshot guess or trusting a call returned without error. CI runs the full suite on macOS, Windows, and Linux (Xvfb) on every push; tests that send real input are gated behind `OPENREACH_ALLOW_LIVE_INPUT=1` locally (CI sets it automatically, since its runner is disposable and a developer's own machine isn't): this was a real problem caught mid-session, when local test runs were clicking and typing on the developer's actual desktop by default.

**Honesty note on verification depth**: macOS was verified interactively this session (real `AXPress` calls, real `CGEventSourceFlagsState` reads, a real stuck-modifier bug found and fixed on a live Mac). Windows and Linux backends were written against documented APIs and are verified only by CI, never watched passing by a human with real hardware. See `GAP_ANALYSIS.md` for the full, current, honest gap list, not a wishlist.

For agent training/eval at scale, see [OSWorld](https://github.com/xlang-ai/OSWorld) (real VM snapshots, ~370 tasks). openreach is the tool-use layer; OSWorld is the benchmark environment you'd point an agent built on openreach at. Not yet run against openreach.

## Status

Functional core: cross-OS pixel actions, OCR grounding, a verified macOS accessibility-tree backend, native keyboard backends on all three OSes (macOS verified live, Windows/Linux CI-only), a focus-verification guard, and a fail-closed safety gate. See `GAP_ANALYSIS.md` for what's still open.

## License

MIT.
