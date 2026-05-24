from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from harness.artifacts import ArtifactQuery, ArtifactStore
from harness.audit import AuditLog, AuditQuery
from harness.checkpoint import WorkspaceCheckpoint
from harness.config import HarnessConfig
from harness.context import ContextManager
from harness.cost import ModelPricing, RuntimeBudget
from harness.doctor import DoctorReport
from harness.eval import EvalExpectation, EvalSuiteStore, evaluate_trace, run_golden_suite
from harness.handoff import HandoffBuilder
from harness.hooks import HookRunner
from harness.kernel import AgentKernel
from harness.memory import MarkdownMemoryStore
from harness.model import FakeModelClient, OpenAICompatibleModelClient
from harness.permissions import PermissionMode, Policy
from harness.runs import RunStatus, RunStore
from harness.scaffold import scaffold_project
from harness.schema import ModelResponse
from harness.schema import ToolCall
from harness.session import JsonlSessionStore, Session, SessionBundle
from harness.skills import SkillStore
from harness.tasks import TaskStatus, TaskStore
from harness.tools import default_tool_registry
from harness.trace import TraceQuery, TraceRecorder
from harness.verify import VerifyOptions, run_verify
from harness.workspace import Workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness")
    parser.add_argument("--config", help="Optional JSON config file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one local agent turn.")
    run.add_argument("prompt")
    run.add_argument("--workspace")
    run.add_argument("--session-dir")
    run.add_argument("--session")
    run.add_argument("--trace")
    run.add_argument("--audit")
    run.add_argument("--artifact-dir")
    run.add_argument("--memory-dir")
    run.add_argument("--skill-dir")
    run.add_argument("--task-dir")
    run.add_argument("--run-dir")
    run.add_argument("--task-id")
    run.add_argument("--hook-config")
    run.add_argument("--base-url")
    run.add_argument("--api-key")
    run.add_argument("--model")
    run.add_argument("--model-timeout-seconds", type=int)
    run.add_argument("--temperature", type=float)
    run.add_argument("--top-p", type=float)
    run.add_argument("--max-tokens", type=int)
    run.add_argument("--permission", choices=[mode.value for mode in PermissionMode])
    run.add_argument("--tool-profile", choices=["safe", "coding"])
    run.add_argument("--allow-tool", action="append", dest="allowed_tools", default=None)
    run.add_argument("--deny-tool", action="append", dest="denied_tools", default=None)
    run.add_argument("--max-iterations", type=int)
    run.add_argument("--max-model-retries", type=int)
    run.add_argument("--max-total-tokens", type=int)
    run.add_argument("--max-cost-usd", type=float)
    run.add_argument("--sandbox-runner")
    run.add_argument("--fail-fast-on-tool-error", action="store_true", default=None)
    run.add_argument("--checkpoint-before", action="store_true")
    run.add_argument("--checkpoint-dir", default=".harness/checkpoints")
    run.add_argument("--checkpoint-label", default="")
    run.add_argument("--restore-checkpoint-on-failure", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--mock-final", help="Use a fake model response for local smoke tests.")
    run.add_argument("--mock-responses", help="Path to JSON scripted fake model responses.")

    tools = subparsers.add_parser("tools", help="List built-in tools.")
    tools.add_argument("--show")
    tools.add_argument("--call", help="Execute one built-in tool directly.")
    tools.add_argument("--args-json", default="{}", help="JSON object arguments for --call.")
    tools.add_argument("--args-file", help="Path to a JSON object arguments file for --call.")
    tools.add_argument("--workspace")
    tools.add_argument("--permission", choices=[mode.value for mode in PermissionMode])
    tools.add_argument("--tool-profile", choices=["safe", "coding"])
    tools.add_argument("--audit")
    tools.add_argument("--allow-tool", action="append", dest="allowed_tools", default=None)
    tools.add_argument("--deny-tool", action="append", dest="denied_tools", default=None)
    tools.add_argument("--max-output-chars", type=int)
    tools.add_argument("--max-file-read-bytes", type=int)
    tools.add_argument("--default-bash-timeout-seconds", type=int)
    tools.add_argument("--max-bash-timeout-seconds", type=int)
    tools.add_argument("--sandbox-runner")
    tools.add_argument("--json", action="store_true")

    config_cmd = subparsers.add_parser("config", help="Show and validate merged harness config.")
    config_cmd.add_argument("--show", action="store_true")
    config_cmd.add_argument("--validate", action="store_true")
    config_cmd.add_argument("--json", action="store_true")

    sessions = subparsers.add_parser("sessions", help="List local sessions.")
    sessions.add_argument("--session-dir")
    sessions.add_argument("--show", help="Show one session summary.")
    sessions.add_argument("--history", help="Show all saved snapshots for one session.")
    sessions.add_argument("--export", dest="export_session", help="Export one session to a JSON bundle.")
    sessions.add_argument("--import", dest="import_session", help="Import a session JSON bundle.")
    sessions.add_argument("--compact", help="Compact and persist one session.")
    sessions.add_argument("--dry-run", action="store_true")
    sessions.add_argument("--workspace-contains")
    sessions.add_argument("--limit", type=int)
    sessions.add_argument("--json", action="store_true")
    sessions.add_argument("--max-messages", type=int)
    sessions.add_argument("--keep-head", type=int)
    sessions.add_argument("--keep-tail", type=int)
    sessions.add_argument("--output")

    memory = subparsers.add_parser("memory", help="Add or search local markdown memory.")
    memory.add_argument("--memory-dir")
    memory.add_argument("--add")
    memory.add_argument("--search")
    memory.add_argument("--list", action="store_true")
    memory.add_argument("--clear", action="store_true")

    skills = subparsers.add_parser("skills", help="Add, search, or render local markdown skills.")
    skills.add_argument("--skill-dir")
    skills.add_argument("--add")
    skills.add_argument("--description", default="")
    skills.add_argument("--body")
    skills.add_argument("--body-file")
    skills.add_argument("--search")
    skills.add_argument("--show")
    skills.add_argument("--delete")
    skills.add_argument("--query")

    tasks = subparsers.add_parser("tasks", help="Create, update, list, and show local harness tasks.")
    tasks.add_argument("--task-dir")
    tasks.add_argument("--add")
    tasks.add_argument("--description", default="")
    tasks.add_argument("--update")
    tasks.add_argument("--show")
    tasks.add_argument("--history")
    tasks.add_argument("--delete")
    tasks.add_argument("--status", choices=[status.value for status in TaskStatus])
    tasks.add_argument("--session")
    tasks.add_argument("--json", action="store_true")

    runs = subparsers.add_parser("runs", help="List and show local harness run records.")
    runs.add_argument("--run-dir")
    runs.add_argument("--enqueue")
    runs.add_argument("--run-next", action="store_true")
    runs.add_argument("--run-until-empty", action="store_true")
    runs.add_argument("--max-runs", type=int)
    runs.add_argument("--workspace")
    runs.add_argument("--task-id")
    runs.add_argument("--cancel")
    runs.add_argument("--reason", default="")
    runs.add_argument("--show")
    runs.add_argument("--diagnose")
    runs.add_argument("--session-dir")
    runs.add_argument("--trace")
    runs.add_argument("--audit")
    runs.add_argument("--mock-final")
    runs.add_argument("--mock-responses")
    runs.add_argument("--permission", choices=[mode.value for mode in PermissionMode])
    runs.add_argument("--tool-profile", choices=["safe", "coding"])
    runs.add_argument("--max-iterations", type=int)
    runs.add_argument("--status", choices=[status.value for status in RunStatus])
    runs.add_argument("--session")
    runs.add_argument("--limit", type=int)
    runs.add_argument("--json", action="store_true")

    trace = subparsers.add_parser("trace", help="Summarize a trace JSONL file.")
    trace.add_argument("--trace")
    trace.add_argument("--session")
    trace.add_argument("--turn")
    trace.add_argument("--type", dest="event_type")
    trace.add_argument("--limit", type=int)
    trace.add_argument("--sessions", action="store_true")
    trace.add_argument("--failures-only", action="store_true")
    trace.add_argument("--json", action="store_true")

    eval_cmd = subparsers.add_parser("eval", help="Evaluate a trace JSONL file.")
    eval_cmd.add_argument("--trace")
    eval_cmd.add_argument("--expect-stop-reason")
    eval_cmd.add_argument("--max-tool-errors", type=int)
    eval_cmd.add_argument("--require-tool", action="append", default=[])
    eval_cmd.add_argument("--final-text-contains")
    eval_cmd.add_argument("--max-total-tokens", type=int)
    eval_cmd.add_argument("--max-cost-usd", type=float)

    golden = subparsers.add_parser("golden", help="Run a golden trace regression suite.")
    golden.add_argument("suite")

    eval_suite = subparsers.add_parser("eval-suite", help="Manage and run golden trace suites.")
    eval_suite.add_argument("suite")
    eval_suite.add_argument("--add")
    eval_suite.add_argument("--add-from-trace")
    eval_suite.add_argument("--list", action="store_true")
    eval_suite.add_argument("--run", action="store_true")
    eval_suite.add_argument("--trace-path")
    eval_suite.add_argument("--expect-stop-reason")
    eval_suite.add_argument("--max-tool-errors", type=int)
    eval_suite.add_argument("--require-tool", action="append", default=[])
    eval_suite.add_argument("--final-text-contains")
    eval_suite.add_argument("--max-total-tokens", type=int)
    eval_suite.add_argument("--max-cost-usd", type=float)

    artifacts = subparsers.add_parser("artifacts", help="Register, list, and verify local artifacts.")
    artifacts.add_argument("--artifact-dir")
    artifacts.add_argument("--workspace")
    artifacts.add_argument("--register", help="Path to a file to register.")
    artifacts.add_argument("--kind", default="file")
    artifacts.add_argument("--path-contains")
    artifacts.add_argument("--limit", type=int)
    artifacts.add_argument("--json", action="store_true")
    artifacts.add_argument("--verify", help="Artifact id to verify.")
    artifacts.add_argument("--verify-all", action="store_true")

    audit = subparsers.add_parser("audit", help="Print audit JSONL events.")
    audit.add_argument("--audit")
    audit.add_argument("--session")
    audit.add_argument("--turn")
    audit.add_argument("--type", dest="event_type")
    audit.add_argument("--action")
    audit.add_argument("--allowed", choices=["true", "false"])
    audit.add_argument("--limit", type=int)
    audit.add_argument("--summary", action="store_true")
    audit.add_argument("--json", action="store_true")

    replay = subparsers.add_parser("replay", help="Print trace events as a compact timeline.")
    replay.add_argument("--trace")
    replay.add_argument("--session")
    replay.add_argument("--type", dest="event_type")
    replay.add_argument("--limit", type=int)

    handoff = subparsers.add_parser("handoff", help="Render a markdown handoff for a session.")
    handoff.add_argument("--session-dir")
    handoff.add_argument("--task-dir")
    handoff.add_argument("--trace")
    handoff.add_argument("--session", required=True)
    handoff.add_argument("--output")

    checkpoint = subparsers.add_parser("checkpoint", help="Create or restore workspace checkpoints.")
    checkpoint.add_argument("--workspace")
    checkpoint.add_argument("--checkpoint-dir", default=".harness/checkpoints")
    checkpoint.add_argument("--artifact-dir")
    checkpoint.add_argument("--label", default="")
    checkpoint.add_argument("--restore", help="Path to a checkpoint manifest.json to restore.")
    checkpoint.add_argument("--diff", help="Compare the workspace to a checkpoint manifest.json.")
    checkpoint.add_argument(
        "--clean",
        action="store_true",
        help="Remove files not present in the checkpoint during restore.",
    )

    doctor = subparsers.add_parser("doctor", help="Print local harness diagnostics.")
    doctor.add_argument("--workspace")
    doctor.add_argument("--session-dir")
    doctor.add_argument("--memory-dir")
    doctor.add_argument("--skill-dir")
    doctor.add_argument("--task-dir")
    doctor.add_argument("--run-dir")
    doctor.add_argument("--trace")
    doctor.add_argument("--audit")
    doctor.add_argument("--artifact-dir")
    doctor.add_argument("--sandbox-runner")
    doctor.add_argument("--json", action="store_true")

    verify = subparsers.add_parser("verify", help="Run local verification gates.")
    verify.add_argument("--work-dir", default=".harness/verify")
    verify.add_argument("--skip-tests", action="store_true")
    verify.add_argument("--skip-compile", action="store_true")
    verify.add_argument("--skip-config-validation", action="store_true")
    verify.add_argument("--skip-mock-smoke", action="store_true")
    verify.add_argument("--live-smoke", action="store_true")
    verify.add_argument("--live-tool-smoke", action="store_true")

    init = subparsers.add_parser("init", help="Create a local harness config and sample fixtures.")
    init.add_argument("--root", default=".harness-local")
    init.add_argument("--overwrite", action="store_true")

    return parser


def build_kernel(args: argparse.Namespace) -> tuple[AgentKernel, Session]:
    config = _merged_config(args)
    workspace = Workspace(config.workspace)
    store = JsonlSessionStore(config.session_dir)
    session = store.load(args.session) if args.session else None
    if session is None:
        session = Session.new(workspace=str(workspace.root))
    if args.mock_responses:
        model = FakeModelClient(_load_mock_responses(args.mock_responses))
    elif args.mock_final is not None:
        model = FakeModelClient([ModelResponse(content=args.mock_final)])
    else:
        model = OpenAICompatibleModelClient(
            base_url=_require(config.base_url, "--base-url, config base_url, or HARNESS_BASE_URL"),
            api_key=_require(config.api_key, "--api-key, config api_key, or HARNESS_API_KEY"),
            model=config.model,
            timeout_seconds=config.model_timeout_seconds,
            temperature=config.temperature,
            top_p=config.top_p,
            max_tokens=config.max_tokens,
        )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(
            max_output_chars=config.max_output_chars,
            max_file_read_bytes=config.max_file_read_bytes,
            default_bash_timeout_seconds=config.default_bash_timeout_seconds,
            max_bash_timeout_seconds=config.max_bash_timeout_seconds,
            sandbox_runner=config.sandbox_runner,
            tool_profile=config.tool_profile,
        ),
        store=store,
        workspace=workspace,
        policy=Policy(
            PermissionMode(config.permission),
            approval_callback=_approval_callback,
            allowed_tools=set(config.allowed_tools) if config.allowed_tools is not None else None,
            denied_tools=set(config.denied_tools) if config.denied_tools is not None else None,
            audit=AuditLog(config.audit),
        ),
        context=ContextManager(),
        trace=TraceRecorder(config.trace),
        audit=AuditLog(config.audit),
        memory=MarkdownMemoryStore(config.memory_dir),
        skills=SkillStore(config.skill_dir),
        task_context=_task_context(config, getattr(args, "task_id", None)),
        hooks=HookRunner.from_config(config.hook_config, cwd=workspace.root),
        pricing=ModelPricing(
            input_cost_per_million_tokens=config.input_cost_per_million_tokens,
            output_cost_per_million_tokens=config.output_cost_per_million_tokens,
        ),
        budget=RuntimeBudget(
            max_total_tokens=config.max_total_tokens,
            max_cost_usd=config.max_cost_usd,
        ),
        max_iterations=config.max_iterations,
        max_model_retries=config.max_model_retries,
        fail_fast_on_tool_error=config.fail_fast_on_tool_error,
    )
    return kernel, session


def _merged_config(args: argparse.Namespace) -> HarnessConfig:
    config = HarnessConfig.load(getattr(args, "config", None))
    for attr in (
        "workspace",
        "session_dir",
        "trace",
        "audit",
        "artifact_dir",
        "memory_dir",
        "skill_dir",
        "task_dir",
        "run_dir",
        "hook_config",
        "base_url",
        "api_key",
        "model",
        "model_timeout_seconds",
        "temperature",
        "top_p",
        "max_tokens",
        "permission",
        "tool_profile",
        "allowed_tools",
        "denied_tools",
        "max_output_chars",
        "max_file_read_bytes",
        "default_bash_timeout_seconds",
        "max_bash_timeout_seconds",
        "sandbox_runner",
        "fail_fast_on_tool_error",
        "max_iterations",
        "max_model_retries",
        "input_cost_per_million_tokens",
        "output_cost_per_million_tokens",
        "max_total_tokens",
        "max_cost_usd",
    ):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(config, attr, value)
    return config


def _approval_callback(action: str, required: PermissionMode) -> bool:
    sys.stderr.write(f"Approve {action} requiring {required.value}? [y/N] ")
    sys.stderr.flush()
    try:
        answer = input()
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _require(value: str | None, label: str) -> str:
    if not value:
        raise SystemExit(f"missing required {label}")
    return value


def _load_mock_responses(path: str | Path) -> list[ModelResponse]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    responses: list[ModelResponse] = []
    for item in data:
        responses.append(
            ModelResponse(
                content=item.get("content") or "",
                tool_calls=[
                    ToolCall(
                        id=call["id"],
                        name=call["name"],
                        arguments=dict(call.get("arguments") or {}),
                    )
                    for call in item.get("tool_calls", [])
                ],
                usage=dict(item.get("usage") or {}),
            )
        )
    return responses


def _load_tool_arguments(args: argparse.Namespace) -> dict:
    source = (
        Path(args.args_file).read_text(encoding="utf-8")
        if args.args_file
        else args.args_json
    )
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid tool arguments JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("tool arguments must be a JSON object")
    return payload


def _task_context(config: HarnessConfig, task_id: str | None) -> str:
    if not task_id:
        return ""
    try:
        return TaskStore(config.task_dir).render_context(task_id)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc


def _eval_expect_dict(args: argparse.Namespace) -> dict:
    expect: dict = {}
    if args.expect_stop_reason is not None:
        expect["stop_reason"] = args.expect_stop_reason
    if args.max_tool_errors is not None:
        expect["max_tool_errors"] = args.max_tool_errors
    if args.require_tool:
        expect["required_tools"] = args.require_tool
    if args.final_text_contains is not None:
        expect["final_text_contains"] = args.final_text_contains
    if args.max_total_tokens is not None:
        expect["max_total_tokens"] = args.max_total_tokens
    if args.max_cost_usd is not None:
        expect["max_cost_usd"] = args.max_cost_usd
    return expect


def _print_task(task) -> None:  # noqa: ANN001 - keep CLI formatting decoupled from task dataclass.
    print(f"task: {task.id}")
    print(f"title: {task.title}")
    print(f"status: {task.status}")
    if task.description:
        print(f"description: {task.description}")
    if task.session_id:
        print(f"session: {task.session_id}")


def _session_snapshot_summary(index: int, session: Session) -> dict:
    last = session.messages[-1] if session.messages else None
    return {
        "index": index,
        "id": session.id,
        "workspace": session.workspace,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": len(session.messages),
        "usage_prompt_tokens": int(session.usage.get("prompt_tokens", 0)),
        "usage_completion_tokens": int(session.usage.get("completion_tokens", 0)),
        "usage_total_tokens": int(session.usage.get("total_tokens", 0)),
        "cost_usd": session.cost_usd,
        "last_role": last.role if last else None,
        "last_content": last.content if last else "",
        "metadata": dict(session.metadata),
    }


def _session_summary_dict(session: Session) -> dict:
    last = session.messages[-1] if session.messages else None
    return {
        "id": session.id,
        "workspace": session.workspace,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": len(session.messages),
        "usage": dict(session.usage),
        "cost_usd": session.cost_usd,
        "last_role": last.role if last else None,
        "last_content": last.content if last else "",
        "metadata": dict(session.metadata),
    }


def _run_record_dict(record) -> dict:  # noqa: ANN001 - CLI stays decoupled from run dataclass.
    data = record.to_dict()
    if record.ended_at is not None:
        data["duration_seconds"] = max(0.0, record.ended_at - record.started_at)
    else:
        data["duration_seconds"] = None
    return data


def _prepare_worker_run_args(args: argparse.Namespace, record) -> None:  # noqa: ANN001
    args.prompt = record.prompt
    args.workspace = record.workspace
    args.session = None
    args.task_id = record.task_id
    for name, value in {
        "base_url": None,
        "api_key": None,
        "model": None,
        "model_timeout_seconds": None,
        "temperature": None,
        "top_p": None,
        "max_tokens": None,
        "allowed_tools": None,
        "denied_tools": None,
        "max_model_retries": None,
        "max_total_tokens": None,
        "max_cost_usd": None,
        "sandbox_runner": None,
        "fail_fast_on_tool_error": None,
        "artifact_dir": None,
        "memory_dir": None,
        "skill_dir": None,
        "task_dir": None,
        "hook_config": None,
    }.items():
        if not hasattr(args, name):
            setattr(args, name, value)


def _run_queued_record(args: argparse.Namespace, config: HarnessConfig, runs: RunStore, record) -> dict:  # noqa: ANN001
    _prepare_worker_run_args(args, record)
    kernel, session = build_kernel(args)
    runs.start(record.id, session_id=session.id)
    task_store = TaskStore(config.task_dir) if record.task_id else None
    if record.task_id and task_store is not None:
        task_store.update(record.task_id, status=TaskStatus.IN_PROGRESS, session_id=session.id)
    result = kernel.run_turn(session, record.prompt)
    completed = runs.finish(
        record.id,
        status=RunStatus.SUCCEEDED if result.stop_reason == "final_answer" else RunStatus.FAILED,
        session_id=result.session_id,
        turn_id=result.turn_id,
        stop_reason=result.stop_reason,
        iterations=result.iterations,
    )
    if record.task_id and task_store is not None:
        task_store.update(
            record.task_id,
            status=TaskStatus.DONE if result.stop_reason == "final_answer" else TaskStatus.BLOCKED,
            session_id=result.session_id,
            metadata={
                "last_stop_reason": result.stop_reason,
                "last_iterations": str(result.iterations),
            },
        )
    return {
        "final_text": result.final_text,
        "run_id": completed.id,
        "session_id": result.session_id,
        "turn_id": result.turn_id,
        "iterations": result.iterations,
        "stop_reason": result.stop_reason,
        "status": completed.status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        config = _merged_config(args)
        run_trace = TraceRecorder(config.trace)
        run_store = RunStore(config.run_dir)
        checkpoint = None
        if args.checkpoint_before or args.restore_checkpoint_on_failure:
            label = args.checkpoint_label or f"before-run-{args.prompt[:40]}"
            checkpoint = WorkspaceCheckpoint.create(config.workspace, args.checkpoint_dir, label=label)
            run_trace.record(
                "checkpoint_created",
                checkpoint_id=checkpoint.id,
                manifest_path=str(checkpoint.manifest_path),
                label=checkpoint.label,
                files=len(checkpoint.files),
                workspace=config.workspace,
            )
            if not args.json:
                print(f"checkpoint: {checkpoint.id}")
                print(f"checkpoint_manifest: {checkpoint.manifest_path}")
        kernel, session = build_kernel(args)
        run_record = run_store.create(
            prompt=args.prompt,
            workspace=config.workspace,
            session_id=session.id,
            task_id=args.task_id,
        )
        task_store = TaskStore(config.task_dir) if args.task_id else None
        if args.task_id:
            session.metadata["task_id"] = args.task_id
            task_store.update(
                args.task_id,
                status=TaskStatus.IN_PROGRESS,
                session_id=session.id,
            )
        result = kernel.run_turn(session, args.prompt)
        completed_run = run_store.finish(
            run_record.id,
            status=RunStatus.SUCCEEDED if result.stop_reason == "final_answer" else RunStatus.FAILED,
            session_id=result.session_id,
            turn_id=result.turn_id,
            stop_reason=result.stop_reason,
            iterations=result.iterations,
        )
        if args.task_id and task_store is not None:
            final_status = TaskStatus.DONE if result.stop_reason == "final_answer" else TaskStatus.BLOCKED
            task_store.update(
                args.task_id,
                status=final_status,
                session_id=result.session_id,
                metadata={
                    "last_stop_reason": result.stop_reason,
                    "last_iterations": str(result.iterations),
                },
            )
        restored_checkpoint_id = None
        if (
            checkpoint is not None
            and args.restore_checkpoint_on_failure
            and result.stop_reason != "final_answer"
        ):
            WorkspaceCheckpoint.restore(checkpoint.manifest_path, config.workspace, clean=True)
            restored_checkpoint_id = checkpoint.id
            run_trace.record(
                "checkpoint_restored",
                checkpoint_id=checkpoint.id,
                manifest_path=str(checkpoint.manifest_path),
                workspace=config.workspace,
                stop_reason=result.stop_reason,
            )
            if not args.json:
                print(f"restored_checkpoint: {checkpoint.id}")
        if args.json:
            print(
                json.dumps(
                    {
                        "final_text": result.final_text,
                        "run_id": completed_run.id,
                        "session_id": result.session_id,
                        "turn_id": result.turn_id,
                        "iterations": result.iterations,
                        "stop_reason": result.stop_reason,
                        "checkpoint_id": checkpoint.id if checkpoint is not None else None,
                        "checkpoint_manifest": str(checkpoint.manifest_path) if checkpoint is not None else None,
                        "restored_checkpoint_id": restored_checkpoint_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(result.final_text)
            print(f"\nrun: {completed_run.id}")
            print(f"\nsession: {result.session_id}")
            print(f"stop_reason: {result.stop_reason}")
        return 0 if result.stop_reason == "final_answer" else 2
    if args.command == "tools":
        config = _merged_config(args)
        tools = default_tool_registry(
            max_output_chars=config.max_output_chars,
            max_file_read_bytes=config.max_file_read_bytes,
            default_bash_timeout_seconds=config.default_bash_timeout_seconds,
            max_bash_timeout_seconds=config.max_bash_timeout_seconds,
            sandbox_runner=config.sandbox_runner,
            tool_profile=config.tool_profile,
        )
        if args.call:
            try:
                tool = tools.get(args.call)
            except KeyError as exc:
                raise SystemExit(str(exc)) from exc
            result = tool.run(
                _load_tool_arguments(args),
                Workspace(config.workspace),
                Policy(
                    PermissionMode(config.permission),
                    allowed_tools=(
                        set(config.allowed_tools) if config.allowed_tools is not None else None
                    ),
                    denied_tools=(
                        set(config.denied_tools) if config.denied_tools is not None else None
                    ),
                    audit=AuditLog(config.audit),
                ),
            )
            if args.json:
                print(
                    json.dumps(
                        {
                            "name": args.call,
                            "is_error": result.is_error,
                            "output": result.output,
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print(result.output)
            return 1 if result.is_error else 0
        if args.show:
            try:
                description = tools.describe(args.show)
            except KeyError as exc:
                raise SystemExit(str(exc)) from exc
            if args.json:
                print(json.dumps(description, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"name: {description['name']}")
                print(f"description: {description['description']}")
                print(f"required_permission: {description['required_permission']}")
                print(f"category: {description['category']}")
                print(f"sandbox_required: {description['sandbox_required']}")
                print("parameters:")
                print(json.dumps(description["parameters"], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.json:
            print(json.dumps(tools.definitions(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        for name in tools.names():
            print(name)
        return 0
    if args.command == "config":
        config = _merged_config(args)
        issues = config.validate()
        if args.json:
            payload = {}
            if args.show or not args.validate:
                payload["config"] = config.redacted_dict()
            if args.validate:
                payload["issues"] = [asdict(issue) for issue in issues]
                payload["valid"] = not any(issue.level == "error" for issue in issues)
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            if args.show or not args.validate:
                for key, value in config.redacted_dict().items():
                    print(f"{key}: {value}")
            if args.validate:
                for issue in issues:
                    print(f"{issue.level}: {issue.key} - {issue.message}")
                print(f"valid: {not any(issue.level == 'error' for issue in issues)}")
        return 0 if not any(issue.level == "error" for issue in issues) else 1
    if args.command == "sessions":
        config = _merged_config(args)
        store = JsonlSessionStore(config.session_dir)
        if args.export_session:
            if not args.output:
                raise SystemExit("--output is required with --export")
            session = store.load(args.export_session)
            if session is None:
                raise SystemExit(f"session not found: {args.export_session}")
            path = SessionBundle.export(session, args.output)
            print(f"exported: {path}")
        elif args.import_session:
            session = SessionBundle.import_into(args.import_session, store)
            print(f"imported: {session.id}")
        elif args.compact:
            session = store.load(args.compact)
            if session is None:
                raise SystemExit(f"session not found: {args.compact}")
            manager = ContextManager(
                max_messages=args.max_messages or 40,
                keep_head=args.keep_head if args.keep_head is not None else 2,
                keep_tail=args.keep_tail if args.keep_tail is not None else 20,
            )
            try:
                result = manager.compact(session.messages)
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            if not args.dry_run:
                session.messages = result.messages
                session.metadata["compacted"] = "true"
                session.metadata["last_compaction_dropped_messages"] = str(result.dropped_count)
                store.save(session)
            print(f"session: {session.id}")
            print(f"original_messages: {result.original_count}")
            print(f"messages: {len(result.messages)}")
            print(f"dropped_messages: {result.dropped_count}")
            print(f"dry_run: {args.dry_run}")
        elif args.show:
            session = store.load(args.show)
            if session is None:
                raise SystemExit(f"session not found: {args.show}")
            print(f"session: {session.id}")
            print(f"workspace: {session.workspace}")
            print(f"messages: {len(session.messages)}")
            print(f"usage_prompt_tokens: {session.usage.get('prompt_tokens', 0)}")
            print(f"usage_completion_tokens: {session.usage.get('completion_tokens', 0)}")
            print(f"usage_total_tokens: {session.usage.get('total_tokens', 0)}")
            print(f"cost_usd: {session.cost_usd:.6f}")
            last = session.messages[-1] if session.messages else None
            if last:
                print(f"last_{last.role}: {last.content}")
        elif args.history:
            snapshots = store.history(args.history)
            if not snapshots:
                raise SystemExit(f"session not found: {args.history}")
            rows = [_session_snapshot_summary(index, snapshot) for index, snapshot in enumerate(snapshots, start=1)]
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            for row in rows:
                last_role = row.get("last_role") or ""
                print(
                    f"{row['index']} messages={row['messages']} "
                    f"updated_at={row['updated_at']} last_role={last_role}"
                )
        else:
            summaries = store.summaries(workspace_contains=args.workspace_contains, limit=args.limit)
            if args.json:
                print(json.dumps(summaries, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            for summary in summaries:
                print(summary["id"])
        return 0
    if args.command == "memory":
        config = _merged_config(args)
        memory = MarkdownMemoryStore(config.memory_dir)
        if args.add:
            memory.add(args.add)
            print("added")
        if args.list:
            for item in memory.list():
                print(item)
        if args.clear:
            memory.clear()
            print("cleared")
        if args.search:
            for item in memory.search(args.search):
                print(item)
        if not args.add and not args.search and not args.list and not args.clear:
            print(memory.render_context())
        return 0
    if args.command == "skills":
        config = _merged_config(args)
        skills = SkillStore(config.skill_dir)
        if args.add:
            body = args.body
            if args.body_file:
                body = Path(args.body_file).read_text(encoding="utf-8")
            if body is None:
                raise SystemExit("--body or --body-file is required with --add")
            path = skills.add(args.add, body, description=args.description)
            print(f"added: {path.stem}")
            print(f"path: {path}")
            return 0
        if args.search:
            for skill in skills.search(args.search):
                suffix = f": {skill.description}" if skill.description else ""
                print(f"{skill.name}{suffix}")
            return 0
        if args.show:
            skill = skills.get(args.show)
            if skill is None:
                raise SystemExit(f"skill not found: {args.show}")
            print(f"name: {skill.name}")
            if skill.description:
                print(f"description: {skill.description}")
            print(skill.body)
            return 0
        if args.delete:
            if not skills.delete(args.delete):
                raise SystemExit(f"skill not found: {args.delete}")
            print(f"deleted: {args.delete}")
            return 0
        print(skills.render_context(args.query or ""))
        return 0
    if args.command == "tasks":
        config = _merged_config(args)
        tasks = TaskStore(config.task_dir)
        if args.add:
            task = tasks.create(args.add, description=args.description)
            _print_task(task)
            return 0
        if args.update:
            task = tasks.update(
                args.update,
                status=args.status,
                session_id=args.session,
                description=args.description if args.description else None,
            )
            _print_task(task)
            return 0
        if args.show:
            try:
                task = tasks.load(args.show)
            except KeyError as exc:
                raise SystemExit(str(exc)) from exc
            if args.json:
                print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            _print_task(task)
            return 0
        if args.history:
            try:
                history = tasks.history(args.history)
            except KeyError as exc:
                raise SystemExit(str(exc)) from exc
            if args.json:
                print(json.dumps(history, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            for event in history:
                print(f"{event.get('type')} {event.get('changes')}")
            return 0
        if args.delete:
            if not tasks.delete(args.delete):
                raise SystemExit(f"task not found: {args.delete}")
            print(f"deleted: {args.delete}")
            return 0
        task_list = tasks.list(status=args.status, session_id=args.session)
        if args.json:
            print(json.dumps([task.to_dict() for task in task_list], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        for task in task_list:
            print(f"{task.id} {task.status} {task.title}")
        return 0
    if args.command == "runs":
        config = _merged_config(args)
        runs = RunStore(config.run_dir)
        if args.enqueue:
            record = runs.enqueue(prompt=args.enqueue, workspace=args.workspace or config.workspace, task_id=args.task_id)
            payload = _run_record_dict(record)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            print(f"enqueued: {record.id}")
            print(f"status: {record.status}")
            return 0
        if args.cancel:
            try:
                record = runs.cancel(args.cancel, reason=args.reason)
            except (KeyError, ValueError) as exc:
                raise SystemExit(str(exc)) from exc
            payload = _run_record_dict(record)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            print(f"cancelled: {record.id}")
            return 0
        if args.run_next:
            pending = runs.list(status=RunStatus.PENDING)
            if not pending:
                raise SystemExit("no pending runs")
            payload = _run_queued_record(args, config, runs, pending[0])
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(payload["final_text"])
                print(f"\nrun: {payload['run_id']}")
                print(f"session: {payload['session_id']}")
                print(f"stop_reason: {payload['stop_reason']}")
            return 0 if payload["stop_reason"] == "final_answer" else 2
        if args.run_until_empty:
            if args.max_runs is not None and args.max_runs < 0:
                raise SystemExit("--max-runs must be >= 0")
            results = []
            while args.max_runs is None or len(results) < args.max_runs:
                pending = runs.list(status=RunStatus.PENDING)
                if not pending:
                    break
                results.append(_run_queued_record(args, config, runs, pending[0]))
            succeeded = sum(1 for item in results if item["status"] == RunStatus.SUCCEEDED.value)
            failed = sum(1 for item in results if item["status"] == RunStatus.FAILED.value)
            payload = {
                "processed": len(results),
                "succeeded": succeeded,
                "failed": failed,
                "runs": results,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"processed: {payload['processed']}")
                print(f"succeeded: {payload['succeeded']}")
                print(f"failed: {payload['failed']}")
                for item in results:
                    print(f"{item['run_id']} {item['status']} stop_reason={item['stop_reason']}")
            return 0 if failed == 0 else 2
        if args.diagnose:
            try:
                record = runs.load(args.diagnose)
            except KeyError as exc:
                raise SystemExit(str(exc)) from exc
            session = JsonlSessionStore(config.session_dir).load(record.session_id) if record.session_id else None
            payload = {
                "run": _run_record_dict(record),
                "session": _session_summary_dict(session) if session else None,
                "trace_summary": TraceQuery(TraceRecorder(config.trace)).summary(
                    session_id=record.session_id,
                    turn_id=record.turn_id,
                ),
                "audit_summary": AuditQuery(AuditLog(config.audit)).summary(
                    session_id=record.session_id,
                    turn_id=record.turn_id,
                ),
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            print(f"run: {record.id}")
            print(f"status: {record.status}")
            print(f"stop_reason: {record.stop_reason or ''}")
            print(f"session: {record.session_id or ''}")
            print(f"turn: {record.turn_id or ''}")
            print("trace:")
            for key, value in payload["trace_summary"].items():
                print(f"  {key}: {value}")
            print("audit:")
            for key, value in payload["audit_summary"].items():
                print(f"  {key}: {value}")
            return 0
        if args.show:
            try:
                record = runs.load(args.show)
            except KeyError as exc:
                raise SystemExit(str(exc)) from exc
            payload = _run_record_dict(record)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            print(f"run: {record.id}")
            print(f"status: {record.status}")
            print(f"session: {record.session_id or ''}")
            print(f"turn: {record.turn_id or ''}")
            print(f"stop_reason: {record.stop_reason or ''}")
            print(f"iterations: {record.iterations}")
            print(f"workspace: {record.workspace}")
            print(f"prompt: {record.prompt}")
            return 0
        records = runs.list(status=args.status, session_id=args.session, limit=args.limit)
        if args.json:
            print(json.dumps([_run_record_dict(record) for record in records], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        for record in records:
            print(
                f"{record.id} {record.status} session={record.session_id or ''} "
                f"turn={record.turn_id or ''} stop_reason={record.stop_reason or ''}"
            )
        return 0
    if args.command == "trace":
        config = _merged_config(args)
        query = TraceQuery(TraceRecorder(config.trace))
        if args.sessions:
            sessions = query.sessions(failures_only=args.failures_only)
            if args.session:
                sessions = [session for session in sessions if session["session_id"] == args.session]
            if args.limit is not None:
                sessions = sessions[-args.limit:]
            if args.json:
                print(json.dumps(sessions, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            for session in sessions:
                print(
                    f"{session['session_id']} {session.get('stop_reason')} "
                    f"turns={session['turns']} model_calls={session['model_calls']} "
                    f"tool_calls={session['tool_calls']} tool_errors={session['tool_errors']} "
                    f"tokens={session['total_tokens']} cost_usd={session['cost_usd']:.6f}"
                )
            return 0
        if args.json:
            print(
                json.dumps(
                    query.events(
                        session_id=args.session,
                        turn_id=args.turn,
                        event_type=args.event_type,
                        limit=args.limit,
                    ),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        summary = query.summary(session_id=args.session, turn_id=args.turn, event_type=args.event_type)
        for key, value in summary.items():
            print(f"{key}: {value}")
        return 0
    if args.command == "eval":
        config = _merged_config(args)
        report = evaluate_trace(
            config.trace,
            EvalExpectation(
                stop_reason=args.expect_stop_reason,
                max_tool_errors=args.max_tool_errors,
                required_tools=args.require_tool,
                final_text_contains=args.final_text_contains,
                max_total_tokens=args.max_total_tokens if args.max_total_tokens is not None else config.max_total_tokens,
                max_cost_usd=args.max_cost_usd if args.max_cost_usd is not None else config.max_cost_usd,
            ),
        )
        for key, value in report.checks.items():
            print(f"{key}: {value}")
        print(f"passed: {report.passed}")
        return 0 if report.passed else 1
    if args.command == "golden":
        report = run_golden_suite(args.suite)
        for case in report.cases:
            status = "passed" if case.report.passed else "failed"
            print(f"{case.name}: {status}")
            for key, value in case.report.checks.items():
                print(f"  {key}: {value}")
        print(f"passed: {report.passed}")
        print(f"cases: {report.passed_count}/{report.total}")
        return 0 if report.passed else 1
    if args.command == "eval-suite":
        store = EvalSuiteStore(args.suite)
        if args.add_from_trace:
            if not args.trace_path:
                raise SystemExit("--trace-path is required with --add-from-trace")
            store.add_case_from_trace(args.add_from_trace, trace=args.trace_path)
            print(f"added: {args.add_from_trace}")
            return 0
        if args.add:
            if not args.trace_path:
                raise SystemExit("--trace-path is required with --add")
            expect = _eval_expect_dict(args)
            store.add_case(args.add, trace=args.trace_path, expect=expect)
            print(f"added: {args.add}")
            return 0
        if args.list:
            for case in store.list_cases():
                print(f"{case.get('name')} {case.get('trace')}")
            return 0
        if args.run:
            report = store.run()
            for case in report.cases:
                status = "passed" if case.report.passed else "failed"
                print(f"{case.name}: {status}")
            print(f"passed: {report.passed}")
            print(f"cases: {report.passed_count}/{report.total}")
            return 0 if report.passed else 1
        raise SystemExit("choose one of --add, --add-from-trace, --list, or --run")
    if args.command == "artifacts":
        config = _merged_config(args)
        store = ArtifactStore(config.artifact_dir)
        if args.register:
            artifact = store.register_file(
                args.register,
                workspace_root=args.workspace or config.workspace,
                kind=args.kind,
            )
            print(f"artifact: {artifact.id}")
            print(f"path: {artifact.relative_path}")
            print(f"sha256: {artifact.sha256}")
            return 0
        if args.verify:
            print(f"verified: {store.verify(args.verify)}")
            return 0
        if args.verify_all:
            report = store.verify_all()
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            for item in report:
                print(f"{item['id']} {item['status']} {item['relative_path']}")
            return 0
        artifacts = ArtifactQuery(store).artifacts(
            kind=args.kind if args.kind != "file" or args.path_contains or args.limit or args.json else None,
            path_contains=args.path_contains,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps([asdict(artifact) for artifact in artifacts], ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        for artifact in artifacts:
            print(f"{artifact.id} {artifact.kind} {artifact.relative_path} {artifact.size}")
        return 0
    if args.command == "audit":
        config = _merged_config(args)
        query = AuditQuery(AuditLog(config.audit))
        allowed = None if args.allowed is None else args.allowed == "true"
        if args.summary:
            summary = query.summary(
                session_id=args.session,
                turn_id=args.turn,
                event_type=args.event_type,
                action=args.action,
                allowed=allowed,
            )
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
                return 0
            print(f"events: {summary['events']}")
            print(f"allowed: {summary['allowed']}")
            print(f"denied: {summary['denied']}")
            for event_type, count in summary["by_type"].items():
                print(f"type.{event_type}: {count}")
            for action, count in summary["by_action"].items():
                print(f"action.{action}: {count}")
            return 0
        events = query.events(
            session_id=args.session,
            turn_id=args.turn,
            event_type=args.event_type,
            action=args.action,
            allowed=allowed,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps(events, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        for event in events:
            event_type = event.get("type")
            action = event.get("action", "")
            allowed = event.get("allowed")
            suffix = "" if allowed is None else f" allowed={allowed}"
            print(f"{event_type} {action}{suffix}".strip())
        return 0
    if args.command == "replay":
        config = _merged_config(args)
        query = TraceQuery(TraceRecorder(config.trace))
        for event in query.events(session_id=args.session, event_type=args.event_type, limit=args.limit):
            event_type = event.get("type")
            if event_type == "turn_start":
                print(f"turn_start {event.get('session_id')} {event.get('user_input')}")
            elif event_type == "tool_call":
                status = "error" if event.get("is_error") else "ok"
                print(f"tool_call {event.get('name')} {status}")
            elif event_type == "turn_end":
                print(f"turn_end {event.get('stop_reason')} {event.get('final_text')}")
            else:
                print(str(event_type))
        return 0
    if args.command == "handoff":
        config = _merged_config(args)
        session = JsonlSessionStore(config.session_dir).load(args.session)
        if session is None:
            raise SystemExit(f"session not found: {args.session}")
        task = None
        task_id = session.metadata.get("task_id")
        if task_id:
            try:
                task = TaskStore(config.task_dir).load(task_id)
            except KeyError:
                task = None
        text = HandoffBuilder().render(
            session=session,
            task=task,
            trace_summary=TraceRecorder(config.trace).summary(),
        )
        if args.output:
            Path(args.output).expanduser().write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    if args.command == "checkpoint":
        config = _merged_config(args)
        if args.diff:
            diff = WorkspaceCheckpoint.diff(args.diff, config.workspace)
            print(f"clean: {diff.clean}")
            for label, paths in (
                ("added", diff.added),
                ("modified", diff.modified),
                ("deleted", diff.deleted),
                ("unchanged", diff.unchanged),
            ):
                if paths:
                    print(f"{label}: {', '.join(paths)}")
                else:
                    print(f"{label}:")
        elif args.restore:
            checkpoint = WorkspaceCheckpoint.restore(
                args.restore,
                config.workspace,
                clean=args.clean,
            )
            print(f"restored: {checkpoint.id}")
            print(f"files: {len(checkpoint.files)}")
        else:
            checkpoint = WorkspaceCheckpoint.create(config.workspace, args.checkpoint_dir, label=args.label)
            print(f"checkpoint: {checkpoint.id}")
            print(f"manifest: {checkpoint.manifest_path}")
            print(f"files: {len(checkpoint.files)}")
            if args.artifact_dir or config.artifact_dir:
                artifact = ArtifactStore(args.artifact_dir or config.artifact_dir).register_file(
                    checkpoint.manifest_path,
                    workspace_root=checkpoint.root,
                    kind="checkpoint-manifest",
                )
                print(f"artifact: {artifact.id}")
        return 0
    if args.command == "doctor":
        config = _merged_config(args)
        tools = default_tool_registry(tool_profile=config.tool_profile)
        report = DoctorReport.build(
            workspace=config.workspace,
            session_dir=config.session_dir,
            memory_dir=config.memory_dir,
            skill_dir=config.skill_dir,
            task_dir=config.task_dir,
            run_dir=config.run_dir,
            trace=config.trace,
            audit=config.audit,
            artifact_dir=config.artifact_dir,
            base_url=config.base_url,
            api_key=config.api_key,
            tools_count=len(tools.names()),
            sandbox_runner=config.sandbox_runner,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "overall": report.ok,
                        "checks": {
                            name: {
                                "ok": check.ok,
                                "level": "ok" if check.ok else check.level,
                                "message": check.message,
                            }
                            for name, check in report.checks.items()
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        for name, check in report.checks.items():
            status = "ok" if check.ok else check.level
            print(f"{name}: {status} - {check.message}")
        print(f"overall: {report.ok}")
        return 0
    if args.command == "verify":
        config = _merged_config(args)
        report = run_verify(
            VerifyOptions(
                root=Path.cwd(),
                work_dir=Path(args.work_dir),
                run_config_validation=not args.skip_config_validation,
                run_tests=not args.skip_tests,
                run_compile=not args.skip_compile,
                run_mock_smoke=not args.skip_mock_smoke,
                run_live_smoke=args.live_smoke,
                run_live_tool_smoke=args.live_tool_smoke,
                config=config,
            )
        )
        for name, result in report.results.items():
            status = "passed" if result.passed else "failed"
            print(f"{name}: {status}")
            if not result.passed and result.output:
                print(result.output)
        print(f"overall: {report.passed}")
        return 0 if report.passed else 1
    if args.command == "init":
        result = scaffold_project(args.root, overwrite=args.overwrite)
        print(f"root: {result.root}")
        print(f"config: {result.config_path}")
        print(f"mock_responses: {result.mock_responses_path}")
        print(f"golden: {result.golden_path}")
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
