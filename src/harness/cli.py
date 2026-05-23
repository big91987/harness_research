from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.artifacts import ArtifactStore
from harness.audit import AuditLog
from harness.checkpoint import WorkspaceCheckpoint
from harness.config import HarnessConfig
from harness.context import ContextManager
from harness.cost import ModelPricing, RuntimeBudget
from harness.doctor import DoctorReport
from harness.eval import EvalExpectation, evaluate_trace, run_golden_suite
from harness.handoff import HandoffBuilder
from harness.hooks import HookRunner
from harness.kernel import AgentKernel
from harness.memory import MarkdownMemoryStore
from harness.model import FakeModelClient, OpenAICompatibleModelClient
from harness.permissions import PermissionMode, Policy
from harness.scaffold import scaffold_project
from harness.schema import ModelResponse
from harness.schema import ToolCall
from harness.session import JsonlSessionStore, Session
from harness.skills import SkillStore
from harness.tasks import TaskStatus, TaskStore
from harness.tools import default_tool_registry
from harness.trace import TraceRecorder
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
    run.add_argument("--task-id")
    run.add_argument("--hook-config")
    run.add_argument("--base-url")
    run.add_argument("--api-key")
    run.add_argument("--model")
    run.add_argument("--permission", choices=[mode.value for mode in PermissionMode])
    run.add_argument("--allow-tool", action="append", dest="allowed_tools", default=None)
    run.add_argument("--deny-tool", action="append", dest="denied_tools", default=None)
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

    skills = subparsers.add_parser("skills", help="Add, search, or render local markdown skills.")
    skills.add_argument("--skill-dir")
    skills.add_argument("--add")
    skills.add_argument("--description", default="")
    skills.add_argument("--body")
    skills.add_argument("--body-file")
    skills.add_argument("--search")
    skills.add_argument("--query")

    tasks = subparsers.add_parser("tasks", help="Create, update, list, and show local harness tasks.")
    tasks.add_argument("--task-dir")
    tasks.add_argument("--add")
    tasks.add_argument("--description", default="")
    tasks.add_argument("--update")
    tasks.add_argument("--show")
    tasks.add_argument("--status", choices=[status.value for status in TaskStatus])
    tasks.add_argument("--session")

    trace = subparsers.add_parser("trace", help="Summarize a trace JSONL file.")
    trace.add_argument("--trace")

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

    handoff = subparsers.add_parser("handoff", help="Render a markdown handoff for a session.")
    handoff.add_argument("--session-dir")
    handoff.add_argument("--task-dir")
    handoff.add_argument("--trace")
    handoff.add_argument("--session", required=True)
    handoff.add_argument("--output")

    checkpoint = subparsers.add_parser("checkpoint", help="Create or restore workspace checkpoints.")
    checkpoint.add_argument("--workspace")
    checkpoint.add_argument("--checkpoint-dir", default=".harness/checkpoints")
    checkpoint.add_argument("--label", default="")
    checkpoint.add_argument("--restore", help="Path to a checkpoint manifest.json to restore.")

    doctor = subparsers.add_parser("doctor", help="Print local harness diagnostics.")
    doctor.add_argument("--workspace")
    doctor.add_argument("--session-dir")
    doctor.add_argument("--memory-dir")
    doctor.add_argument("--skill-dir")
    doctor.add_argument("--task-dir")

    verify = subparsers.add_parser("verify", help="Run local verification gates.")
    verify.add_argument("--work-dir", default=".harness/verify")
    verify.add_argument("--skip-tests", action="store_true")
    verify.add_argument("--skip-compile", action="store_true")
    verify.add_argument("--skip-mock-smoke", action="store_true")
    verify.add_argument("--live-smoke", action="store_true")

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
        )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(
            max_output_chars=config.max_output_chars,
            max_file_read_bytes=config.max_file_read_bytes,
            default_bash_timeout_seconds=config.default_bash_timeout_seconds,
            max_bash_timeout_seconds=config.max_bash_timeout_seconds,
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
        "hook_config",
        "base_url",
        "api_key",
        "model",
        "permission",
        "allowed_tools",
        "denied_tools",
        "max_output_chars",
        "max_file_read_bytes",
        "default_bash_timeout_seconds",
        "max_bash_timeout_seconds",
        "max_iterations",
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


def _task_context(config: HarnessConfig, task_id: str | None) -> str:
    if not task_id:
        return ""
    try:
        return TaskStore(config.task_dir).render_context(task_id)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc


def _print_task(task) -> None:  # noqa: ANN001 - keep CLI formatting decoupled from task dataclass.
    print(f"task: {task.id}")
    print(f"title: {task.title}")
    print(f"status: {task.status}")
    if task.description:
        print(f"description: {task.description}")
    if task.session_id:
        print(f"session: {task.session_id}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        config = _merged_config(args)
        kernel, session = build_kernel(args)
        if args.task_id:
            session.metadata["task_id"] = args.task_id
            TaskStore(config.task_dir).update(
                args.task_id,
                status=TaskStatus.IN_PROGRESS,
                session_id=session.id,
            )
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
            print(f"usage_prompt_tokens: {session.usage.get('prompt_tokens', 0)}")
            print(f"usage_completion_tokens: {session.usage.get('completion_tokens', 0)}")
            print(f"usage_total_tokens: {session.usage.get('total_tokens', 0)}")
            print(f"cost_usd: {session.cost_usd:.6f}")
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
            _print_task(task)
            return 0
        for task in tasks.list(status=args.status):
            print(f"{task.id} {task.status} {task.title}")
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
            skill_dir=config.skill_dir,
            task_dir=config.task_dir,
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
    if args.command == "verify":
        config = _merged_config(args)
        report = run_verify(
            VerifyOptions(
                root=Path.cwd(),
                work_dir=Path(args.work_dir),
                run_tests=not args.skip_tests,
                run_compile=not args.skip_compile,
                run_mock_smoke=not args.skip_mock_smoke,
                run_live_smoke=args.live_smoke,
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
