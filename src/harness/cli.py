from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from harness.context import ContextManager
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run one local agent turn.")
    run.add_argument("prompt")
    run.add_argument("--workspace", default=".harness/workspace")
    run.add_argument("--session-dir", default=".harness/sessions")
    run.add_argument("--session")
    run.add_argument("--trace", default=".harness/trace.jsonl")
    run.add_argument("--memory-dir", default=".harness/memory")
    run.add_argument("--base-url", default=os.environ.get("HARNESS_BASE_URL") or os.environ.get("OPENAI_BASE_URL"))
    run.add_argument("--api-key", default=os.environ.get("HARNESS_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    run.add_argument("--model", default=os.environ.get("HARNESS_MODEL") or "gpt-4.1-mini")
    run.add_argument("--permission", choices=[mode.value for mode in PermissionMode], default=PermissionMode.READ_ONLY.value)
    run.add_argument("--max-iterations", type=int, default=20)
    run.add_argument("--mock-final", help="Use a fake model response for local smoke tests.")
    run.add_argument("--mock-responses", help="Path to JSON scripted fake model responses.")

    subparsers.add_parser("tools", help="List built-in tools.")

    sessions = subparsers.add_parser("sessions", help="List local sessions.")
    sessions.add_argument("--session-dir", default=".harness/sessions")

    memory = subparsers.add_parser("memory", help="Add or search local markdown memory.")
    memory.add_argument("--memory-dir", default=".harness/memory")
    memory.add_argument("--add")
    memory.add_argument("--search")

    return parser


def build_kernel(args: argparse.Namespace) -> tuple[AgentKernel, Session]:
    workspace = Workspace(args.workspace)
    store = JsonlSessionStore(args.session_dir)
    session = store.load(args.session) if args.session else None
    if session is None:
        session = Session.new(workspace=str(workspace.root))
    if args.mock_responses:
        model = FakeModelClient(_load_mock_responses(args.mock_responses))
    elif args.mock_final is not None:
        model = FakeModelClient([ModelResponse(content=args.mock_final)])
    else:
        model = OpenAICompatibleModelClient(
            base_url=_require(args.base_url, "--base-url or HARNESS_BASE_URL"),
            api_key=_require(args.api_key, "--api-key or HARNESS_API_KEY"),
            model=args.model,
        )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=store,
        workspace=workspace,
        policy=Policy(PermissionMode(args.permission)),
        context=ContextManager(),
        trace=TraceRecorder(args.trace),
        memory=MarkdownMemoryStore(args.memory_dir),
        max_iterations=args.max_iterations,
    )
    return kernel, session


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
        for session_id in JsonlSessionStore(args.session_dir).list():
            print(session_id)
        return 0
    if args.command == "memory":
        memory = MarkdownMemoryStore(args.memory_dir)
        if args.add:
            memory.add(args.add)
            print("added")
        if args.search:
            for item in memory.search(args.search):
                print(item)
        if not args.add and not args.search:
            print(memory.render_context())
        return 0
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
