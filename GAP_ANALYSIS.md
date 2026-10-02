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

## Open, named honestly rather than papered over

| Gap | Why it's not closed | Mirroir's equivalent |
|---|---|---|
| No accessibility-tree / structured element access | pyautogui has no AX-tree reader; this is a multi-day per-OS project (AXUIElement on macOS, UIAutomation on Windows, AT-SPI2 on Linux). Screenshot + OCR is the only perception channel today, same ceiling mirroir hits on the mirrored surface. | Same ceiling: "the mirrored surface exposes zero child accessibility elements." |
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
