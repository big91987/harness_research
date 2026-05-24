# Session Memory Extraction

## Purpose

Local harness sessions should be able to promote durable context into persistent
Markdown memory without requiring a server, TUI, or Web UI. This is the first
local version of the state-layer "dream" path: an operator can extract useful
facts from a completed session and make them available to future turns.

## Behavior

- `memory --extract-session <session-id>` loads a saved session from
  `--session-dir`.
- The configured model receives a transcript and must return JSON only: an array
  of short memory strings, or an object containing `memories`, `items`, or
  `facts`.
- The extractor writes only non-empty, deduplicated items to `memory.md`.
- Duplicate detection ignores a leading bullet, case, and trailing periods.
- Invalid JSON is fail closed: the command exits with an error and does not guess
  from free text.
- The command supports real model configuration through `HARNESS_BASE_URL`,
  `HARNESS_API_KEY`, and `HARNESS_MODEL`; scripted `--mock-final` exists for
  deterministic tests.

## Acceptance

- Unit coverage proves extraction, deduplication, and model prompt construction.
- CLI coverage proves a saved session can be extracted into persistent memory.
- Live validation should run against a real OpenAI-compatible model and confirm
  a durable fact from a session appears in `memory --list`.

