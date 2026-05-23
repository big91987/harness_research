# Minimal Harness

This repository contains a local-first agent harness prototype. It is intentionally small:
no TUI, no Web UI, and no server yet. The current goal is to make the local kernel,
CLI, tools, state, policy, memory, and trace loop reliable before adding a harness server.

## Current Layers

```text
CLI
  -> AgentKernel
  -> ContextManager
  -> ModelClient
  -> ToolRegistry
  -> Policy / Workspace
  -> SessionStore
  -> TraceRecorder
  -> MarkdownMemoryStore
```

Implemented modules:

- `harness.cli`: local command line entry point.
- `harness.kernel`: turn loop, model call, tool dispatch, session persistence, trace events.
- `harness.model`: fake model for tests and OpenAI-compatible chat completions client.
- `harness.tools`: built-in `list_files`, `read_file`, `write_file`, `edit_file`, `grep`, `bash`.
- `harness.permissions`: read-only, workspace-write, danger, and prompt policy modes.
- `harness.workspace`: workspace path containment.
- `harness.session`: JSONL session persistence.
- `harness.context`: simple message compaction.
- `harness.memory`: Markdown-backed persistent memory.
- `harness.trace`: JSONL trajectory/trace events.

## Run Tests

```bash
python3 -m pytest
```

## Local Smoke Test

Final-answer-only fake model:

```bash
PYTHONPATH=src python3 -m harness.cli run "say hi" \
  --workspace /tmp/harness-ws \
  --session-dir /tmp/harness-sessions \
  --trace /tmp/harness-trace.jsonl \
  --mock-final "hi from harness"
```

Tool-loop fake model:

```bash
PYTHONPATH=src python3 -m harness.cli run "create file" \
  --workspace /tmp/harness-ws \
  --session-dir /tmp/harness-sessions \
  --trace /tmp/harness-trace.jsonl \
  --permission workspace-write \
  --mock-responses /path/to/responses.json
```

`responses.json`:

```json
[
  {
    "content": "writing file",
    "tool_calls": [
      {
        "id": "call-1",
        "name": "write_file",
        "arguments": { "path": "out.txt", "content": "ok" }
      }
    ]
  },
  { "content": "created out.txt" }
]
```

## Real Model

Use any OpenAI-compatible `/chat/completions` endpoint:

```bash
export HARNESS_BASE_URL="https://api.example.com"
export HARNESS_API_KEY="..."
export HARNESS_MODEL="model-name"

PYTHONPATH=src python3 -m harness.cli run "list files" \
  --workspace /tmp/harness-ws \
  --permission read-only
```

Do not commit API keys. Keep credentials in environment variables.

## Next Server Phase

The server should wrap the same local modules instead of creating a second runtime:

- HTTP/WebSocket API around `AgentKernel`.
- Session routing and agent registry on top of `JsonlSessionStore`.
- Approval broker for `prompt` mode.
- Trace/replay endpoints for `TraceRecorder`.
- Tool and memory management APIs.

