from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.artifacts import ArtifactStore
from harness.audit import AuditLog
from harness.checkpoint import WorkspaceCheckpoint
from harness.config import HarnessConfig
from harness.context import ContextManager
from harness.doctor import DoctorReport
from harness.eval import EvalExpectation, evaluate_trace, run_golden_suite
from harness.kernel import AgentKernel
from harness.memory import MarkdownMemoryStore
from harness.model import FakeModelClient, OpenAICompatibleModelClient
from harness.permissions import PermissionMode, Policy
from harness.schema import ModelResponse
from harness.schema import ToolCall
from harness.session import JsonlSessionStore, Session
from harness.tools import default_tool_registry
from harness.trace import TraceRecorder
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
    run.add_argument("--base-url")
    run.add_argument("--api-key")
    run.add_argument("--model")
    run.add_argument("--permission", choices=[mode.value for mode in PermissionMode])
    run.add_argument("--max-iterations", type=int)
    run.add_argument("--mock-final", help="Use a fake model response for local smoke tests.")
    run.add_argument("--mock-responses", help="Path to JSON scripted fake model responses.")

    subparsers.add_parser("tools", help="List built-in tools.")

    sessions = subparsers.add_parser("sessions", help="List local sessions.")
    sessions.add_argument("--session-dir")
    sessions.add_argument("--show", help="Show one session summary.")

    memory = subparsers.add_parser("memory", help="Add or search local markdown memory.")
    memory.add_argument("--memory-dir")
    memory.add_argument("--add")
    memory.add_argument("--search")

    trace = subparsers.add_parser("trace", help="Summarize a trace JSONL file.")
    trace.add_argument("--trace")

    eval_cmd = subparsers.add_parser("eval", help="Evaluate a trace JSONL file.")
    eval_cmd.add_argument("--trace")
    eval_cmd.add_argument("--expect-stop-reason")
    eval_cmd.add_argument("--max-tool-errors", type=int)
    eval_cmd.add_argument("--require-tool", action="append", default=[])
    eval_cmd.add_argument("--final-text-contains")

    golden = subparsers.add_parser("golden", help="Run a golden trace regression suite.")
    golden.add_argument("suite")

    artifacts = subparsers.add_parser("artifacts", help="Register, list, and verify local artifacts.")
    artifacts.add_argument("--artifact-dir")
    artifacts.add_argument("--workspace")
    artifacts.add_argument("--register", help="Path to a file to register.")
    artifacts.add_argument("--kind", default="file")
    artifacts.add_argument("--verify", help="Artifact id to verify.")

    audit = subparsers.add_parser("audit", help="Print audit JSONL events.")
    audit.add_argument("--audit")

    replay = subparsers.add_parser("replay", help="Print trace events as a compact timeline.")
    replay.add_argument("--trace")

    checkpoint = subparsers.add_parser("checkpoint", help="Create or restore workspace checkpoints.")
    checkpoint.add_argument("--workspace")
    checkpoint.add_argument("--checkpoint-dir", default=".harness/checkpoints")
    checkpoint.add_argument("--label", default="")
    checkpoint.add_argument("--restore", help="Path to a checkpoint manifest.json to restore.")

    doctor = subparsers.add_parser("doctor", help="Print local harness diagnostics.")
    doctor.add_argument("--workspace")
    doctor.add_argument("--session-dir")
    doctor.add_argument("--memory-dir")

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
        )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=store,
        workspace=workspace,
        policy=Policy(PermissionMode(config.permission), approval_callback=_approval_callback),
        context=ContextManager(),
        trace=TraceRecorder(config.trace),
        audit=AuditLog(config.audit),
        memory=MarkdownMemoryStore(config.memory_dir),
        max_iterations=config.max_iterations,
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
        "base_url",
        "api_key",
        "model",
        "permission",
        "max_iterations",
    ):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(config, attr, value)
    return config


def _approval_callback(action: str, required: PermissionMode) -> bool:
    answer = input(f"Approve {action} requiring {required.value}? [y/N] ")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        kernel, session = build_kernel(args)
        result = kernel.run_turn(session, args.prompt)
        print(result.final_text)
        print(f"\nsession: {result.session_id}")
        print(f"stop_reason: {result.stop_reason}")
        return 0 if result.stop_reason == "final_answer" else 2
    if args.command == "tools":
        for name in default_tool_registry().names():
            print(name)
        return 0
    if args.command == "sessions":
        config = _merged_config(args)
        store = JsonlSessionStore(config.session_dir)
        if args.show:
            session = store.load(args.show)
            if session is None:
                raise SystemExit(f"session not found: {args.show}")
            print(f"session: {session.id}")
            print(f"workspace: {session.workspace}")
            print(f"messages: {len(session.messages)}")
            last = session.messages[-1] if session.messages else None
            if last:
                print(f"last_{last.role}: {last.content}")
        else:
            for session_id in store.list():
                print(session_id)
        return 0
    if args.command == "memory":
        config = _merged_config(args)
        memory = MarkdownMemoryStore(config.memory_dir)
        if args.add:
            memory.add(args.add)
            print("added")
        if args.search:
            for item in memory.search(args.search):
                print(item)
        if not args.add and not args.search:
            print(memory.render_context())
        return 0
    if args.command == "trace":
        config = _merged_config(args)
        summary = TraceRecorder(config.trace).summary()
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
        for artifact in store.list():
            print(f"{artifact.id} {artifact.kind} {artifact.relative_path} {artifact.size}")
        return 0
    if args.command == "audit":
        config = _merged_config(args)
        for event in AuditLog(config.audit).read_events():
            event_type = event.get("type")
            action = event.get("action", "")
            allowed = event.get("allowed")
            suffix = "" if allowed is None else f" allowed={allowed}"
            print(f"{event_type} {action}{suffix}".strip())
        return 0
    if args.command == "replay":
        config = _merged_config(args)
        for event in TraceRecorder(config.trace).read_events():
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
    if args.command == "checkpoint":
        config = _merged_config(args)
        if args.restore:
            checkpoint = WorkspaceCheckpoint.restore(args.restore, config.workspace)
            print(f"restored: {checkpoint.id}")
            print(f"files: {len(checkpoint.files)}")
        else:
            checkpoint = WorkspaceCheckpoint.create(config.workspace, args.checkpoint_dir, label=args.label)
            print(f"checkpoint: {checkpoint.id}")
            print(f"manifest: {checkpoint.manifest_path}")
            print(f"files: {len(checkpoint.files)}")
        return 0
    if args.command == "doctor":
        config = _merged_config(args)
        tools = default_tool_registry()
        report = DoctorReport.build(
            workspace=config.workspace,
            session_dir=config.session_dir,
            memory_dir=config.memory_dir,
            trace=config.trace,
            audit=config.audit,
            artifact_dir=config.artifact_dir,
            base_url=config.base_url,
            api_key=config.api_key,
            tools_count=len(tools.names()),
        )
        for name, check in report.checks.items():
            status = "ok" if check.ok else check.level
            print(f"{name}: {status} - {check.message}")
        print(f"overall: {report.ok}")
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
