from __future__ import annotations

import json
from pathlib import Path

from harness.model import FakeModelClient
from harness.schema import ModelResponse, ToolCall
from harness.session import JsonlSessionStore, Session
from harness.subagents import SubagentRunner, SubagentSpec
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
