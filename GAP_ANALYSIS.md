# Gap analysis

Scored against the 20 documented failure modes in mirroir-mcp's reliability notes (the most
battle-tested computer-use harness on this machine, per Jordan's assessment) and the 8-capability
scorecard it uses for mobile automation. Each row says what openreach does today, not what it
aspires to.

## Closed this session

| Mirroir lesson | openreach status |
|---|---|
| #1 False-pass is the top failure | `wait_for_text` only returns ok after a real OCR re-read confirms the outcome, never on "the call didn't error." |
| #3 Stale frames look like no-ops | `wait_for_text` polls until it gets a result or times out; a wedge detector aborts on N identical frames rather than retrying blind. |
| #7 OCR failure looks like an empty screen | `grounding.py` distinguishes "tesseract unreachable" (a real error) from "no match found" (a real empty result) via `_ocr_available()`. |
| #8 Never exact-match raw OCR | `find_text` case-folds and whitespace-normalizes, and more than one match is reported as an ambiguity, not silently resolved. |
| #11 Budgets belong outside the agent | `wait_for_text` enforces a hard timeout and a wedge detector internally; a harness cannot forget to bound a wait. |
| #13 Per-step artifacts are the highest-leverage investment | `--log-dir` writes a timestamped before/after JSON record per CLI call. |
| #16 Screenshot-pixel vs click-coordinate space can silently diverge | Regression test (`test_screenshot_pixel_space_matches_click_coordinate_space`) asserts the invariant on every CI run, on every OS, not just this Mac. |
| #20 Literal text matching, no entity decoding | `find_text` matches the literal normalized string; documented, no HTML/escape handling to silently diverge from. |
| mirroir's fail-closed destructive-action posture | `safety.py` refuses quit/force-quit/lock/log-out key combos unless `--force` is passed. |

## Closed this session, round 2: the pyautogui keyboard chord bug

Live dogfooding (opening Spotlight, typing into real windows) surfaced a reproducible bug:
`pyautogui.hotkey('cmd', 'a')` on macOS posts the modifier and the main key as separate CGEvents
with a timing gap and never calls `CGEventSetFlags`, so the OS can process them as unrelated
keystrokes. Measured live: it typed a literal "a" instead of selecting all, and separately left Cmd
stuck held at the OS HID level system-wide (confirmed via `CGEventSourceFlagsState`, well after the
call returned), corrupting every subsequent keystroke from any source, not just openreach, into a
Cmd-chord.

Fix: `openreach/input/macos.py`, a native Quartz backend that sets modifier flags directly on the
single key event (the pattern already proven in this toolchain's `logic-mcp`), used automatically
by `Backend._do_key`/`_do_type` in place of pyautogui wherever a native backend exists.
`clear_stuck_modifiers()` runs before AND after every chord (before, because a single attempt
measured unreliable: a deliberately-stuck test read the flag as still set immediately after one
clear call, so it retries with a verify loop) and raises `StuckModifierError` rather than silently
typing into a corrupted state if it can't confirm the clear. Verified via `AXSelectedTextRange`
(exact selection length, not a screenshot) in a real TextEdit document, and via direct
`CGEventSourceFlagsState` reads of the real Mac's keyboard state before and after the full test
suite, not assumed clean.

Windows and Linux don't have a native backend yet; they still use pyautogui's hotkey/typewrite,
which may carry the same or a different class of this bug, unverified.

## Closed this session, round 3: macOS accessibility-tree backend (the row-1 gap)

`openreach/accessibility/macos.py`, fresh-written (not ported from autopilot; see the explicit
licensing decision above) using `AXUIElement`. `openreach tree`/`find`/`press` read the real
accessibility tree (role, title, exact bounds, available actions) and invoke elements directly via
`AXPress`, no coordinate guessing. Verified live against TextEdit's Bold checkbox: `find` located it
by role+title, `press` called `AXUIElementPerformAction(ref, "AXPress")`, and the result was
confirmed by reading `AXValue` back (0 to 1), not by trusting the call returning without error. This
is the exact discipline logic-mcp's docs call out as necessary: an app can report success on
`AXPress` while silently ignoring it, so only a post-action read counts as proof. `find` never
exact-matches title (same #8 discipline as OCR `find_text`), and `press` refuses an ambiguous match
(more than one element) rather than guessing which one.

Windows (UI Automation) and Linux (AT-SPI2) are not implemented; `get_accessibility_backend()`
returns `None` there and the CLI reports that cleanly rather than crashing.

## Closed this session, round 4: Windows and Linux native keyboard backends

`openreach/input/windows.py` (SendInput via ctypes, stdlib only) and `openreach/input/linux.py`
(XTEST via python-xlib) mirror macOS's `press_chord`/`type_text` shape, wired into `Backend`
generically (no platform branching needed in `backend.py`, already dispatched through
`get_native_input()`).

Honest limitation on both: **neither was verified interactively by a human this session.** No
Windows or Linux desktop was available; both were written against documented APIs (Win32
`SendInput`, X11 XTEST) and reviewed, not watched passing with real eyes the way macOS's
`AXSelectedTextRange` checks and direct HID-state reads were. CI (`windows-latest`, `ubuntu-latest`
under Xvfb) is the only verification channel, and that's a materially weaker guarantee than the
macOS backend has. Windows' live test drives real Notepad and reads back via `WM_GETTEXT` (close to
the macOS rigor); Linux's live test is weaker still, a connection/keycode smoke test plus
non-raising chord presses, with no real application's text verified, because adding a text-readback
path on Linux would mean either an AT-SPI dependency this module doesn't otherwise need or a
custom X11 app, and that tradeoff wasn't made this session. Wayland is explicitly out of scope for
`linux.py` (XTEST has no Wayland equivalent); the honest options there, `ydotool` (needs root/a
uinput group) or the libei/xdg-desktop-portal RemoteDesktop path (interactive consent prompt), are
different enough in shape to need their own module.

## Open, named honestly rather than papered over

| Gap | Why it's not closed | Mirroir's equivalent |
|---|---|---|
| Windows/Linux accessibility-tree backend | Only macOS is implemented. Windows needs UI Automation (comtypes or pywinauto per the dual-model plan); Linux needs AT-SPI2 (PyGObject `Atspi`). Neither can be verified live from this Mac; CI is the only check. | Same ceiling: "the mirrored surface exposes zero child accessibility elements." |
| Windows/Linux keyboard chord reliability | Only macOS has a native input backend; Windows/Linux still use pyautogui's hotkey/typewrite, unverified for the same class of bug found and fixed on macOS this session. | N/A |
| No ref persistence across CLI calls | `tree`/`find`/`press` re-walk the tree every invocation (no session, no cached element handles). Correct and simple, but means a long flow re-walks a complex app's tree repeatedly. The dual-model plan's phase-6 `serve` daemon is the fix if this proves too slow in practice; not measured yet. | N/A |
| No focus/settle verification before acting | Live testing repeatedly typed into the wrong window because nothing checked the target app was actually frontmost first. Planned (`focus.py`, a pre-action gate) but not built yet. | mirroir's #9, #17, #18: "ready is a claim, the screenshot is the evidence." |
| No deterministic skill/replay format | openreach is a primitive-level CLI, one command per call; there is no flow-recording or compiled-replay layer. | mirroir has one, and its own data shows compiled replay is a **regression** (0/5 vs 5/5), so this is deliberately not ported. |
| No screen-classification before grounding | `find_text` has no concept of "is this an icon grid vs a toolbar" the way mirroir's tap-offset heuristic does; openreach does not apply positional heuristics at all, so this class of bug (#4) does not exist here, but neither does the convenience it buys. | N/A, intentionally not replicated. |
| No prompt-injection handling in the harness layer | openreach returns raw OCR text; it is the calling harness's job to treat that text as untrusted data, not an instruction. Not enforceable at the tool layer. | Documented in mirroir's safety.md as the caller's responsibility too. |
| Wayland (Linux) input | `pyautogui` needs X11; Wayland needs `ydotool` or similar, not yet wired. CI runs ubuntu-latest under Xvfb (X11), so this gap is real but untested by CI today. |

## What was verified empirically, not assumed

- `mss` screenshot pixel dimensions and `pyautogui`'s coordinate space were measured equal on this
  Mac (1440x900 both) before any grounding code was written, specifically because mirroir's #16
  describes a device where they were not.
- `tesseract` 5.5.2 and `pytesseract` 5.5.2 were confirmed installed and reachable before the
  grounding module was built around them, not after.
- A test that sent a real `cmd+q` to this Mac's live desktop during the test run was caught and
  fixed (stubbed the backend) before being reported as passing; see the commit history for the
  before/after.

## Not yet run: OSWorld

OSWorld (`xlang-ai/OSWorld`) is the real benchmark for this class of tool, ~370 tasks against real
VM snapshots. It has not been run against openreach yet; doing so is the next real measurement, not
unit-test coverage.
