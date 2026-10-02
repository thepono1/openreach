# openreach

Open-source, cross-OS computer-use tool for any LLM harness. Screenshot, click, type, scroll: on macOS, Windows, or Linux, through one tool-call contract.

## Why

Anthropic's computer-use tool schema (`screenshot`, `left_click`, `type`, `key`, `scroll`, `cursor_position`, `wait`, ...) is the de facto standard any agent harness already speaks. The reference server-side implementation is closed; the OS automation underneath it doesn't need to be. openreach implements that same contract as a small, testable, MIT-licensed library any harness can call.

## Design

- `src/openreach/schema.py`: the tool-call contract (action names, params), matching Anthropic's computer-use schema so openreach is a drop-in backend for any harness already speaking it.
- `src/openreach/backend.py`: the OS automation implementation. Day one: `pyautogui` + `mss`, which genuinely works unmodified on macOS, Windows, and Linux. Native per-OS backends (accessibility-tree grounding, etc.) are a documented extension point, not a blocker to shipping.
- `src/openreach/server.py`: thin MCP server exposing the schema, so any MCP-speaking harness (Claude Code, Claude Desktop, custom agents) can use openreach directly.

## Testing philosophy

Every claim is a test. The same canonical task suite (`tests/tasks/`) runs against every OS in CI (GitHub Actions matrix: macos-latest, windows-latest, ubuntu-latest via Xvfb). "Cross-OS" is not a claim in this README, it's a CI badge.

For agent training/eval at scale, see [OSWorld](https://github.com/xlang-ai/OSWorld) (real VM snapshots, ~370 tasks). openreach is the tool-use layer; OSWorld is the benchmark environment you'd point an agent built on openreach at.

## Status

Scaffolding. See `src/openreach/`.

## License

MIT.
