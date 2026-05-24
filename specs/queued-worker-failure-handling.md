# Queued Worker Failure Handling

## Purpose

The local run queue must be safe to drain repeatedly before a harness server
exists. A queued record should never remain indefinitely `pending` or
`in_progress` after the worker has selected it and an execution/setup error
occurs.

## Behavior

- `runs --run-next` and `runs --run-until-empty` execute pending records through
  the same helper.
- Worker commands accept explicit local state paths such as `--session-dir`,
  `--task-dir`, `--memory-dir`, `--skill-dir`, `--artifact-dir`, and
  `--hook-config` so a standalone worker can hydrate the same local harness
  state as `run`.
- If kernel construction, task hydration, task state update, or turn execution
  raises an error, the worker finishes the selected run as:
  - `status=failed`
  - `stop_reason=worker_error`
  - `iterations=0`
  - `metadata.worker_error=<message>`
  - `metadata.worker_error_type=<exception type>`
- JSON worker output remains machine-readable for both success and failure.

## Acceptance

- CLI coverage proves a queued run with an invalid task id becomes a failed run
  with `worker_error` metadata.
- Existing run-next and run-until-empty happy-path tests must continue to pass.
- Full local verification must pass after this change.

