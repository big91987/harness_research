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
  -> SkillStore
  -> TaskStore
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
- `harness.skills`: Markdown-backed skill registry, search, and prompt injection.
- `harness.tasks`: local task ledger for long-running work and session association.
- `harness.hooks`: local lifecycle command hooks for harness events.
- `harness.handoff`: Markdown handoff generation for long-running session continuity.
- `harness.trace`: JSONL trajectory/trace events.
- `harness.config`: JSON config loading with environment overrides.
- `harness.cost`: canonical usage normalization and model cost estimation.
- `harness.eval`: simple trace-based regression checks.
- `harness.checkpoint`: workspace snapshot and restore manifests.
- `harness.artifacts`: artifact registration, hash metadata, and verification.
- `harness.audit`: JSONL audit events for tool calls and approvals.

## Run Tests

```bash
python3 -m pytest
```

Run all local verification gates:

```bash
PYTHONPATH=src python3 -m harness.cli verify
```

This runs:

- unit tests
- `compileall`
- a mock end-to-end tool loop smoke test

Live model smoke tests are opt-in only:

```bash
HARNESS_BASE_URL="https://api.example.com" \
HARNESS_API_KEY="..." \
HARNESS_MODEL="model-name" \
PYTHONPATH=src python3 -m harness.cli verify --live-smoke
```

## Bootstrap A Local Harness

Create a runnable local harness directory with config, sample model responses,
and a golden suite:

```bash
PYTHONPATH=src python3 -m harness.cli init --root /tmp/my-harness
```

Run the generated mock scenario:

```bash
PYTHONPATH=src python3 -m harness.cli --config /tmp/my-harness/harness.json run \
  "create sample" \
  --mock-responses /tmp/my-harness/samples/mock_responses.json
```

Validate the generated trace:

```bash
PYTHONPATH=src python3 -m harness.cli golden /tmp/my-harness/samples/golden.json
PYTHONPATH=src python3 -m harness.cli --config /tmp/my-harness/harness.json doctor
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

Export or import a session bundle:

```bash
PYTHONPATH=src python3 -m harness.cli sessions \
  --session-dir /tmp/harness-sessions \
  --export <session-id> \
  --output /tmp/session-bundle.json

PYTHONPATH=src python3 -m harness.cli sessions \
  --session-dir /tmp/other-harness-sessions \
  --import /tmp/session-bundle.json
```

Config-driven run:

```json
{
  "workspace": "/tmp/harness-ws",
  "session_dir": "/tmp/harness-sessions",
  "trace": "/tmp/harness-trace.jsonl",
  "memory_dir": "/tmp/harness-memory",
  "skill_dir": "/tmp/harness-skills",
  "task_dir": "/tmp/harness-tasks",
  "hook_config": "/tmp/harness-hooks.json",
  "permission": "workspace-write",
  "input_cost_per_million_tokens": 0.0,
  "output_cost_per_million_tokens": 0.0,
  "max_total_tokens": 100000,
  "max_cost_usd": 1.0
}
```

```bash
PYTHONPATH=src python3 -m harness.cli --config /tmp/harness.json run "create file" \
  --mock-responses /path/to/responses.json
```

## Diagnostics, Trace, Eval

```bash
PYTHONPATH=src python3 -m harness.cli doctor
PYTHONPATH=src python3 -m harness.cli trace --trace /tmp/harness-trace.jsonl
PYTHONPATH=src python3 -m harness.cli eval \
  --trace /tmp/harness-trace.jsonl \
  --expect-stop-reason final_answer \
  --require-tool write_file \
  --max-tool-errors 0 \
  --max-total-tokens 100000 \
  --max-cost-usd 1.0
```

Run a golden trace suite:

```json
{
  "cases": [
    {
      "name": "write-file-smoke",
      "trace": "/tmp/harness-trace.jsonl",
      "expect": {
        "stop_reason": "final_answer",
        "required_tools": ["write_file"],
        "max_tool_errors": 0,
        "max_total_tokens": 100000,
        "max_cost_usd": 1.0,
        "final_text_contains": "created"
      }
    }
  ]
}
```

```bash
PYTHONPATH=src python3 -m harness.cli golden /tmp/harness-golden.json
```

Manage a golden suite incrementally:

```bash
PYTHONPATH=src python3 -m harness.cli eval-suite /tmp/harness-golden.json \
  --add write-file-smoke \
  --trace-path /tmp/harness-trace.jsonl \
  --expect-stop-reason final_answer \
  --require-tool write_file

PYTHONPATH=src python3 -m harness.cli eval-suite /tmp/harness-golden.json --list
PYTHONPATH=src python3 -m harness.cli eval-suite /tmp/harness-golden.json --run
```

Replay a trace timeline:

```bash
PYTHONPATH=src python3 -m harness.cli replay --trace /tmp/harness-trace.jsonl
```

Filter trace data during debugging:

```bash
PYTHONPATH=src python3 -m harness.cli trace \
  --trace /tmp/harness-trace.jsonl \
  --session <session-id> \
  --type tool_call \
  --json

PYTHONPATH=src python3 -m harness.cli replay \
  --trace /tmp/harness-trace.jsonl \
  --session <session-id> \
  --limit 20
```

Render a handoff for the next session:

```bash
PYTHONPATH=src python3 -m harness.cli handoff \
  --session-dir /tmp/harness-sessions \
  --task-dir /tmp/harness-tasks \
  --trace /tmp/harness-trace.jsonl \
  --session <session-id> \
  --output /tmp/harness-handoff.md
```

The handoff includes task state, session usage/cost, trace summary, and recent
messages so a later run can pick up the work with less manual reconstruction.

Create and restore a workspace checkpoint:

```bash
PYTHONPATH=src python3 -m harness.cli checkpoint \
  --workspace /tmp/harness-ws \
  --checkpoint-dir /tmp/harness-checkpoints \
  --artifact-dir /tmp/harness-artifacts \
  --label before-risky-edit

PYTHONPATH=src python3 -m harness.cli checkpoint \
  --workspace /tmp/harness-ws \
  --restore /tmp/harness-checkpoints/<checkpoint-id>/manifest.json
```

When `--artifact-dir` is provided, the checkpoint manifest is registered as a
`checkpoint-manifest` artifact so it can be verified later.

Register and verify artifacts:

```bash
PYTHONPATH=src python3 -m harness.cli artifacts \
  --artifact-dir /tmp/harness-artifacts \
  --workspace /tmp/harness-ws \
  --register /tmp/harness-ws/out.txt

PYTHONPATH=src python3 -m harness.cli artifacts \
  --artifact-dir /tmp/harness-artifacts \
  --verify <artifact-id>

PYTHONPATH=src python3 -m harness.cli artifacts \
  --artifact-dir /tmp/harness-artifacts \
  --kind checkpoint-manifest \
  --path-contains manifest \
  --json
```

Inspect audit events:

```bash
PYTHONPATH=src python3 -m harness.cli audit --audit /tmp/harness-audit.jsonl

PYTHONPATH=src python3 -m harness.cli audit \
  --audit /tmp/harness-audit.jsonl \
  --session <session-id> \
  --type tool_call \
  --allowed false \
  --json
```

Add and inspect local skills:

```bash
PYTHONPATH=src python3 -m harness.cli skills \
  --skill-dir /tmp/harness-skills \
  --add pytest-debug \
  --description "Debug Python tests" \
  --body "Run focused pytest checks before broad verification."

PYTHONPATH=src python3 -m harness.cli skills \
  --skill-dir /tmp/harness-skills \
  --search python
```

Skills are stored as Markdown files and injected into the model context when they
match the current user request.

Manage long-running tasks:

```bash
PYTHONPATH=src python3 -m harness.cli tasks \
  --task-dir /tmp/harness-tasks \
  --add "ship local harness" \
  --description "track the implementation until verified"

PYTHONPATH=src python3 -m harness.cli run "continue work" \
  --task-dir /tmp/harness-tasks \
  --task-id <task-id> \
  --mock-final "checkpoint complete"
```

`run --task-id` marks the task `in_progress`, records the session id on the task,
and injects the active task into the model context. When the turn ends, a final
answer marks the task `done`; other stop reasons mark it `blocked` and store the
last stop reason in task metadata. Follow-up turns and future server APIs therefore
have both a stable state anchor and task-aware prompts.

Configure lifecycle hooks:

```json
{
  "hooks": [
    {
      "event": "turn_end",
      "command": ["python3", "/tmp/harness-hook.py"],
      "timeout_seconds": 5
    }
  ]
}
```

```bash
PYTHONPATH=src python3 -m harness.cli run "say hi" \
  --hook-config /tmp/harness-hooks.json \
  --mock-final "hi"
```

Hook commands receive event JSON on stdin. They are executed without a shell,
and failures are recorded as `hook_result` trace events instead of blocking the turn.

Doctor checks local writability and harness readiness:

```bash
PYTHONPATH=src python3 -m harness.cli doctor
```

`prompt` permission mode asks for approval before mutating or dangerous tools:

```bash
PYTHONPATH=src python3 -m harness.cli run "edit file" --permission prompt
```

Restrict tools with allow/deny lists:

```bash
PYTHONPATH=src python3 -m harness.cli run "inspect only" \
  --permission danger \
  --allow-tool read_file \
  --allow-tool grep

PYTHONPATH=src python3 -m harness.cli run "no shell" \
  --permission danger \
  --deny-tool bash
```

Configure resource limits in `harness.json`:

```json
{
  "max_output_chars": 20000,
  "max_file_read_bytes": 1000000,
  "default_bash_timeout_seconds": 30,
  "max_bash_timeout_seconds": 120,
  "max_model_retries": 1
}
```

These limits protect the active context from large files, binary files, long-running
commands, and transient model failures. `HARNESS_MAX_MODEL_RETRIES` overrides the
JSON value.

Configure cost tracking in `harness.json` or environment variables:

```json
{
  "input_cost_per_million_tokens": 1.0,
  "output_cost_per_million_tokens": 2.0,
  "max_total_tokens": 100000,
  "max_cost_usd": 1.0
}
```

`HARNESS_INPUT_COST_PER_MILLION_TOKENS`, `HARNESS_OUTPUT_COST_PER_MILLION_TOKENS`,
`HARNESS_MAX_TOTAL_TOKENS`, and `HARNESS_MAX_COST_USD` override the JSON values.
The kernel aggregates usage and cost into sessions, and trace eval/golden suites can
fail runs that exceed token or cost budgets. During a live run, `max_total_tokens`
and `max_cost_usd` also act as runtime guards: once the accumulated session usage
crosses either limit, the kernel stops the turn with `budget_exceeded` before
executing any additional tool calls.

Kernel failure behavior:

- Unknown tools are converted into tool-result errors and returned to the model.
- Model failures are recorded in trace and end the turn with `model_error`.
- Transient model failures can be retried; each retry is recorded as `model_retry`.
- Invalid model tool-call arguments produce explicit protocol errors instead of obscure JSON failures.
- Session state aggregates provider usage fields: `prompt_tokens`, `completion_tokens`, and `total_tokens`.
- Session state also aggregates estimated cost when model pricing is configured.
- Relevant Markdown skills are injected into the system context for each turn.
- Local tasks track long-running work, inject active task context, auto-update from run results, and can be associated with agent sessions.
- Handoff documents summarize active task, session, trace, and recent messages for continuity.
- Runtime budget overruns stop the turn before additional tool calls execute.
- Lifecycle hooks can observe `turn_start`, `tool_call`, and `turn_end` events.
- Tool calls, tool errors, model calls, model responses, and turn endings are recorded as JSONL.
- Tool outputs are bounded before they are returned to the model, so large files or commands do not explode the active context.
- Tool calls are also written to an audit log when configured.
- Policy denials and approval decisions are written to the audit log when configured.

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
- Tool, task, skill, and memory management APIs.
