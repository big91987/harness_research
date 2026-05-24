from __future__ import annotations

import json
from pathlib import Path

from harness.kernel import AgentKernel
from harness.model import FakeModelClient
from harness.permissions import PermissionMode, Policy
from harness.schema import ModelResponse, ToolCall
from harness.session import JsonlSessionStore, Session
from harness.subagents import SubagentRegistry, SubagentRunner, SubagentSpec
from harness.tools import default_tool_registry
from harness.trace import TraceRecorder
from harness.workspace import Workspace


def test_subagent_runner_creates_child_session_and_trace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    store = JsonlSessionStore(tmp_path / "sessions")
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    parent = Session.new(workspace=str(workspace.root))
    model = FakeModelClient([ModelResponse(content="child done")])
    runner = SubagentRunner(
        spec=SubagentSpec(name="researcher"),
        model=model,
        tools=default_tool_registry(tool_profile="safe"),
        store=store,
        workspace=workspace,
        trace=trace,
    )

    result = runner.delegate("inspect repository", parent_session_id=parent.id)

    child = store.load(result.session_id)
    assert result.final_text == "child done"
    assert result.stop_reason == "final_answer"
    assert child is not None
    assert child.metadata["subagent_name"] == "researcher"
    assert child.metadata["parent_session_id"] == parent.id
    events = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(event["type"] == "subagent_start" and event["parent_session_id"] == parent.id for event in events)
    assert any(event["type"] == "subagent_end" and event["child_session_id"] == result.session_id for event in events)


def test_subagent_runner_defaults_to_read_only_policy(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    model = FakeModelClient(
        [
            ModelResponse(
                content="trying write",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="write_file",
                        arguments={"path": "subagent.txt", "content": "bad"},
                    )
                ],
            ),
            ModelResponse(content="write denied"),
        ]
    )
    runner = SubagentRunner(
        spec=SubagentSpec(name="auditor"),
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        trace=TraceRecorder(tmp_path / "trace.jsonl"),
    )

    result = runner.delegate("try to write")

    assert result.final_text == "write denied"
    assert not (workspace.root / "subagent.txt").exists()
    assert "requires workspace-write permission" in model.calls[1][-1].content


def test_delegate_task_tool_runs_named_subagent(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    store = JsonlSessionStore(tmp_path / "sessions")
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    child_model = FakeModelClient([ModelResponse(content="child result")])
    registry = SubagentRegistry()
    registry.register(
        SubagentSpec(name="researcher"),
        model=child_model,
        tools=default_tool_registry(tool_profile="safe"),
        store=store,
        workspace=workspace,
        trace=trace,
    )
    parent_tools = default_tool_registry(tool_profile="safe")
    parent_tools.register(registry.delegate_task_tool(parent_session_id="parent-1"))
    parent_model = FakeModelClient(
        [
            ModelResponse(
                content="delegating",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="delegate_task",
                        arguments={"agent": "researcher", "prompt": "inspect docs"},
                    )
                ],
            ),
            ModelResponse(content="parent done"),
        ]
    )
    kernel = AgentKernel(
        model=parent_model,
        tools=parent_tools,
        store=store,
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
        trace=trace,
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "delegate")

    assert result.final_text == "parent done"
    tool_message = parent_model.calls[1][-1].content
    assert "child result" in tool_message
    assert '"agent": "researcher"' in tool_message
    child_sessions = [store.load(session_id) for session_id in store.list()]
    assert any(session and session.metadata.get("parent_session_id") == "parent-1" for session in child_sessions)
