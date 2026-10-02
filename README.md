# openreach

Open-source, cross-OS computer-use tool for any LLM harness. Screenshot, click, type, scroll: on macOS, Windows, or Linux, through one tool-call contract.

## Why

Anthropic's computer-use tool schema (`screenshot`, `left_click`, `type`, `key`, `scroll`, `cursor_position`, `wait`, ...) is the de facto standard any agent harness already speaks. The reference server-side implementation is closed; the OS automation underneath it doesn't need to be. openreach implements that same contract as a small, testable, MIT-licensed library any harness can call.

## Design

- `src/openreach/schema.py`: the tool-call contract (action names, params), matching Anthropic's computer-use schema so openreach is a drop-in backend for any harness already speaking it.
- `src/openreach/backend.py`: the OS automation implementation. Day one: `pyautogui` + `mss`, which genuinely works unmodified on macOS, Windows, and Linux. Native per-OS backends (accessibility-tree grounding, etc.) are a documented extension point, not a blocker to shipping.
- `src/openreach/cli.py`: the `openreach` command. Any harness drives the desktop by shelling out to it (`openreach screenshot`, `openreach click 100,200`, `openreach type "hello"`), JSON on stdout, exit code 0/1. No MCP server, no daemon: a plain CLI any process on any OS can call.

## CLI

```
pip install -e .
openreach screenshot          # PNG, base64-encoded, on stdout as JSON
openreach position
openreach click 100,200
openreach double-click 100,200
openreach drag 100,200 300,400
openreach scroll down --amount 5 --at 100,200
openreach type "hello world"
openreach key "cmd+c"
openreach wait 1.5
```

## Testing philosophy

Every claim is a test. The same canonical task suite (`tests/tasks/`) runs against every OS in CI (GitHub Actions matrix: macos-latest, windows-latest, ubuntu-latest via Xvfb). "Cross-OS" is not a claim in this README, it's a CI badge.

For agent training/eval at scale, see [OSWorld](https://github.com/xlang-ai/OSWorld) (real VM snapshots, ~370 tasks). openreach is the tool-use layer; OSWorld is the benchmark environment you'd point an agent built on openreach at.

## Status

Scaffolding. See `src/openreach/`.

## License

MIT.
