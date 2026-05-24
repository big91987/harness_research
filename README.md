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
  -> RunStore
```

Implemented modules:

- `harness.cli`: local command line entry point.
- `harness.kernel`: turn loop, model call, tool dispatch, session persistence, trace events.
- `harness.model`: fake model for tests and OpenAI-compatible chat completions client.
- `harness.tools`: built-in `list_files`, `read_file`, `write_file`, `append_file`, `diff_file`, `edit_file`, `move_path`, `make_directory`, `copy_path`, `delete_path`, `grep`, `bash`, `python`.
- `harness.mcp`: Claude/Codex-style `mcpServers` config loading, stdio MCP `initialize` / `tools/list` / `tools/call`, and explicit runtime loading into namespaced MCP tools.
- `harness.sandbox_runner`: stdin/stdout JSON runner entry point for high-risk local execution tools; Phase 1 uses macOS `sandbox-exec` for local bash and Python execution, permits writes only inside the workspace, blocks common host-sensitive reads, and fails closed when the sandbox is unavailable.
- `harness.permissions`: read-only, workspace-write, danger, and prompt policy modes.
- `harness.workspace`: workspace path containment.
- Tool profiles and sandboxing: `safe` exposes read-only inspection tools, `coding` exposes the local coding tool surface; filesystem/search tools are guarded by workspace-scoped parameters, while high-risk execution tools such as `bash` and `python` require a configured sandbox runner and fail closed when it is missing. The built-in runner additionally strips the parent environment, blocks writes outside the workspace, and denies reads from common sensitive host paths through the host macOS sandbox.
- `harness.session`: JSONL session persistence.
- `harness.context`: simple message compaction.
- `harness.memory`: Markdown-backed persistent memory.
- `harness.skills`: Markdown-backed skill registry, search, and prompt injection.
- `harness.tasks`: local task ledger for long-running work and session association.
- `harness.runs`: local run ledger for each CLI turn, including status, session, turn, stop reason, and duration.
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

- config validation
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

Use a real model tool loop when you need to prove the model can actually call
the local coding tools:

```bash
HARNESS_BASE_URL="https://api.example.com" \
HARNESS_API_KEY="..." \
HARNESS_MODEL="model-name" \
PYTHONPATH=src python3 -m harness.cli verify --live-tool-smoke
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
PYTHONPATH=src python3 -m harness.cli --config /tmp/my-harness/harness.json config --validate
PYTHONPATH=src python3 -m harness.cli golden /tmp/my-harness/samples/golden.json
PYTHONPATH=src python3 -m harness.cli --config /tmp/my-harness/harness.json trace --sessions
PYTHONPATH=src python3 -m harness.cli --config /tmp/my-harness/harness.json audit --summary
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

Use `--json` when another process, future server, or UI wrapper needs a stable
result object with `session_id`, `turn_id`, `stop_reason`, `iterations`,
checkpoint fields, and final text:

```bash
PYTHONPATH=src python3 -m harness.cli run "say hi" \
  --workspace /tmp/harness-ws \
  --session-dir /tmp/harness-sessions \
  --trace /tmp/harness-trace.jsonl \
  --mock-final "hi from harness" \
  --json
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

Checkpoint a workspace before a risky run and restore it automatically when the
turn does not reach a final answer:

```bash
PYTHONPATH=src python3 -m harness.cli run "make risky edits" \
  --workspace /tmp/harness-ws \
  --session-dir /tmp/harness-sessions \
  --trace /tmp/harness-trace.jsonl \
  --permission workspace-write \
  --checkpoint-before \
  --checkpoint-dir /tmp/harness-checkpoints \
  --restore-checkpoint-on-failure
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

PYTHONPATH=src python3 -m harness.cli sessions \
  --session-dir /tmp/harness-sessions \
  --workspace-contains harness-ws \
  --json

PYTHONPATH=src python3 -m harness.cli sessions \
  --session-dir /tmp/harness-sessions \
  --history <session-id> \
  --json
```

Session files are append-only JSONL snapshots. `sessions --history` shows each
saved snapshot, which is useful for debugging long tool loops and future resume
flows.

Compact a long session into a persistent summary plus recent messages:

```bash
PYTHONPATH=src python3 -m harness.cli sessions \
  --session-dir /tmp/harness-sessions \
  --compact <session-id> \
  --max-messages 40 \
  --keep-head 2 \
  --keep-tail 20
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
  "tool_profile": "coding",
  "model_timeout_seconds": 120,
  "temperature": 0.2,
  "top_p": 0.9,
  "max_tokens": 4096,
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
PYTHONPATH=src python3 -m harness.cli doctor --json
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

PYTHONPATH=src python3 -m harness.cli eval-suite /tmp/harness-golden.json \
  --add-from-trace write-file-smoke \
  --trace-path /tmp/harness-trace.jsonl

PYTHONPATH=src python3 -m harness.cli eval-suite /tmp/harness-golden.json --list
PYTHONPATH=src python3 -m harness.cli eval-suite /tmp/harness-golden.json --run
```

`--add-from-trace` derives a regression case from the observed trace: stop
reason, called tools, tool error count, final text, and token/cost ceilings.

Replay a trace timeline:

```bash
PYTHONPATH=src python3 -m harness.cli replay --trace /tmp/harness-trace.jsonl
```

Filter trace data during debugging:

```bash
PYTHONPATH=src python3 -m harness.cli trace \
  --trace /tmp/harness-trace.jsonl \
  --session <session-id> \
  --turn <turn-id> \
  --type tool_call \
  --json

PYTHONPATH=src python3 -m harness.cli replay \
  --trace /tmp/harness-trace.jsonl \
  --session <session-id> \
  --limit 20

PYTHONPATH=src python3 -m harness.cli trace \
  --trace /tmp/harness-trace.jsonl \
  --sessions \
  --failures-only
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
  --restore /tmp/harness-checkpoints/<checkpoint-id>/manifest.json \
  --clean
```

Use `--clean` when restore should remove files that were created after the
checkpoint.

The `run` command can also create the checkpoint before a model turn with
`--checkpoint-before`; combine it with `--restore-checkpoint-on-failure` to
roll the workspace back when the turn stops with `model_error`,
`budget_exceeded`, or `max_iterations`.

Review workspace changes before restoring a checkpoint:

```bash
PYTHONPATH=src python3 -m harness.cli checkpoint \
  --workspace /tmp/harness-ws \
  --diff /tmp/harness-checkpoints/<checkpoint-id>/manifest.json
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

PYTHONPATH=src python3 -m harness.cli artifacts \
  --artifact-dir /tmp/harness-artifacts \
  --verify-all \
  --json
```

Inspect audit events:

```bash
PYTHONPATH=src python3 -m harness.cli audit --audit /tmp/harness-audit.jsonl

PYTHONPATH=src python3 -m harness.cli audit \
  --audit /tmp/harness-audit.jsonl \
  --session <session-id> \
  --turn <turn-id> \
  --type tool_call \
  --allowed false \
  --json

PYTHONPATH=src python3 -m harness.cli audit \
  --audit /tmp/harness-audit.jsonl \
  --summary
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

PYTHONPATH=src python3 -m harness.cli skills \
  --skill-dir /tmp/harness-skills \
  --show pytest-debug

PYTHONPATH=src python3 -m harness.cli skills \
  --skill-dir /tmp/harness-skills \
  --delete pytest-debug
```

Skills are stored as Markdown files and injected into the model context when they
match the current user request.

Maintain persistent memory:

```bash
PYTHONPATH=src python3 -m harness.cli memory \
  --memory-dir /tmp/harness-memory \
  --add "Prefer focused pytest runs before full verify."

PYTHONPATH=src python3 -m harness.cli memory \
  --memory-dir /tmp/harness-memory \
  --list

HARNESS_BASE_URL="https://api.example.com" \
HARNESS_API_KEY="..." \
HARNESS_MODEL="model-name" \
PYTHONPATH=src python3 -m harness.cli memory \
  --memory-dir /tmp/harness-memory \
  --session-dir /tmp/harness-sessions \
  --extract-session <session-id> \
  --json

PYTHONPATH=src python3 -m harness.cli memory \
  --memory-dir /tmp/harness-memory \
  --clear
```

`memory --extract-session` uses the configured model to distill durable facts,
preferences, project constraints, and recurring workflow guidance from a saved
session into Markdown memory. It deduplicates against existing memory and rejects
non-JSON extraction responses instead of guessing.

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

PYTHONPATH=src python3 -m harness.cli tasks \
  --task-dir /tmp/harness-tasks \
  --session <session-id> \
  --json

PYTHONPATH=src python3 -m harness.cli tasks \
  --task-dir /tmp/harness-tasks \
  --history <task-id> \
  --json

PYTHONPATH=src python3 -m harness.cli tasks \
  --task-dir /tmp/harness-tasks \
  --delete <task-id>
```

`run --task-id` marks the task `in_progress`, records the session id on the task,
and injects the active task into the model context. When the turn ends, a final
answer marks the task `done`; other stop reasons mark it `blocked` and store the
last stop reason in task metadata. Follow-up turns and future server APIs therefore
have both a stable state anchor and task-aware prompts.
Tasks also keep an append-only history of create/update changes so long-running
work has an auditable state trail.

Inspect run records:

```bash
PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --workspace /tmp/harness-ws \
  --session <session-id> \
  --enqueue "queued prompt" \
  --json

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --cancel <run-id> \
  --reason "no longer needed" \
  --json

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --session-dir /tmp/harness-sessions \
  --task-dir /tmp/harness-tasks \
  --trace /tmp/harness-trace.jsonl \
  --audit /tmp/harness-audit.jsonl \
  --run-next \
  --json

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --session-dir /tmp/harness-sessions \
  --trace /tmp/harness-trace.jsonl \
  --audit /tmp/harness-audit.jsonl \
  --run-until-empty \
  --max-runs 10 \
  --json

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --status failed \
  --json

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --show <run-id> \
  --json

PYTHONPATH=src python3 -m harness.cli runs \
  --run-dir /tmp/harness-runs \
  --session-dir /tmp/harness-sessions \
  --trace /tmp/harness-trace.jsonl \
  --audit /tmp/harness-audit.jsonl \
  --diagnose <run-id> \
  --json
```

Every `run` command creates a run record before the kernel starts and finishes it
after the turn ends. Records include the session id, turn id, stop reason,
iteration count, status, and duration, giving future server or worker code a
stable local run ledger instead of reconstructing runs from trace files.
Pending and cancelled records give future local workers and server APIs a stable
queue-state vocabulary before a network server exists.
Queued records can also carry a `session_id`, so follow-up work can resume the
same conversation context instead of always starting a fresh session.
`runs --run-next` is the minimal local worker: it claims the oldest pending run,
executes it through the same kernel/session/trace/audit path as `run`, and then
marks the record `succeeded` or `failed`.
If worker setup or state hydration fails, the worker marks the queued record
`failed` with `stop_reason=worker_error` and records the error in metadata
instead of leaving it stuck in `pending` or `in_progress`.
`runs --run-until-empty` keeps consuming pending records in FIFO order until the
queue is empty or `--max-runs` is reached. An empty queue is a successful no-op,
which makes it safe for cron-style local workers before the harness server
exists.
`runs --diagnose` joins the run record with session state plus trace/audit
summaries for the same turn, which is the local failure-replay surface before a
server UI exists.

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
PYTHONPATH=src python3 -m harness.cli doctor --json
```

`prompt` permission mode asks for approval before mutating or dangerous tools:

```bash
PYTHONPATH=src python3 -m harness.cli run "edit file" --permission prompt
```

Restrict tools with named profiles and allow/deny lists:

```bash
PYTHONPATH=src python3 -m harness.cli tools --show read_file
PYTHONPATH=src python3 -m harness.cli tools --json
PYTHONPATH=src python3 -m harness.cli tools --tool-profile safe --json

PYTHONPATH=src python3 -m harness.cli run "inspect only" \
  --tool-profile safe \
  --permission read-only

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --call list_files \
  --args-json '{"path":".","pattern":"*.py","max_entries":100,"max_depth":2}'

Inspect stdio MCP servers from a Claude/Codex-style config:

```bash
PYTHONPATH=src python3 -m harness.cli mcp \
  --mcp-config /tmp/harness-mcp.json \
  --list-tools \
  --json
```

Load MCP tools into a local agent turn explicitly:

```bash
PYTHONPATH=src python3 -m harness.cli run "use an MCP tool" \
  --mcp-config /tmp/harness-mcp.json \
  --permission danger \
  --base-url "$HARNESS_BASE_URL" \
  --api-key "$HARNESS_API_KEY" \
  --model "$HARNESS_MODEL"
```

Runtime MCP tools are namespaced as `mcp__server__tool` and require `danger`
permission. The current local implementation marks them as sandbox-required but
does not yet wrap the MCP server process in the sandbox runner.

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --call read_file \
  --args-json '{"path":"large.log","start_line":100,"max_lines":40}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call write_file \
  --args-json '{"path":"out.txt","content":"ok"}' \
  --json

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call append_file \
  --args-json '{"path":"out.txt","content":"\nmore"}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --call diff_file \
  --args-json '{"path":"out.txt","old":"ok","new":"OK","replace_all":true}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --call grep \
  --args-json '{"query":"TODO","path":".","pattern":"*.py","max_matches":20,"context_lines":2,"case_sensitive":false}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call edit_file \
  --args-json '{"path":"out.txt","old":"ok","new":"OK","replace_all":true}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call make_directory \
  --args-json '{"path":"archive"}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call move_path \
  --args-json '{"source":"out.txt","destination":"archive/out.txt"}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call copy_path \
  --args-json '{"source":"archive/out.txt","destination":"archive/out.copy.txt"}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission workspace-write \
  --call delete_path \
  --args-json '{"path":"archive","recursive":true}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission danger \
  --sandbox-runner "python3 -m harness.sandbox_runner" \
  --call bash \
  --args-json '{"command":"printf \"$HARNESS_MODE\"","cwd":"pkg","env":{"HARNESS_MODE":"local"}}'

PYTHONPATH=src python3 -m harness.cli tools \
  --workspace /tmp/harness-ws \
  --permission danger \
  --sandbox-runner "python3 -m harness.sandbox_runner" \
  --call python \
  --args-json '{"code":"from pathlib import Path\nPath(\"out.txt\").write_text(\"py-ok\")\nprint(Path(\"out.txt\").read_text())"}'

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
  "tool_profile": "coding",
  "sandbox_runner": "python3 -m harness.sandbox_runner",
  "model_timeout_seconds": 120,
  "max_model_retries": 1,
  "temperature": 0.2,
  "top_p": 0.9,
  "max_tokens": 4096
}
```

These limits protect the active context from large files, binary files, long-running
commands, slow model providers, and transient model failures.
`HARNESS_MODEL_TIMEOUT_SECONDS`, `HARNESS_MAX_MODEL_RETRIES`,
`HARNESS_TEMPERATURE`, `HARNESS_TOP_P`, `HARNESS_MAX_TOKENS`, and
`HARNESS_TOOL_PROFILE` and `HARNESS_SANDBOX_RUNNER` override the JSON values.
`safe` limits the model to `list_files`, `read_file`, `diff_file`, and `grep`;
`coding` exposes the full local coding set. High-risk execution tools such as
`bash` fail closed when no sandbox runner is configured; file tools still rely
on workspace path guarding and resource limits.

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
- `--fail-fast-on-tool-error` stops the current batch of parallel tool calls after the first tool error and records `tool_batch_aborted`.
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
