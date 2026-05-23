from pathlib import Path

from harness.audit import AuditLog
from harness.kernel import AgentKernel
from harness.model import FakeModelClient
from harness.permissions import PermissionMode, Policy
from harness.schema import ModelResponse, ToolCall
from harness.session import JsonlSessionStore, Session
from harness.tools import default_tool_registry
from harness.trace import TraceRecorder
from harness.workspace import Workspace


def test_kernel_runs_tool_loop_and_persists_trace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    store = JsonlSessionStore(tmp_path / "sessions")
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    audit = AuditLog(tmp_path / "audit.jsonl")
    model = FakeModelClient(
        [
            ModelResponse(
                content="I will write the file.",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="write_file",
                        arguments={"path": "answer.txt", "content": "42"},
                    )
                ],
            ),
            ModelResponse(content="done"),
        ]
    )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=store,
        workspace=workspace,
        policy=Policy(PermissionMode.WORKSPACE_WRITE),
        trace=trace,
        audit=audit,
    )

    session = Session.new(workspace=str(workspace.root))
    result = kernel.run_turn(session, "create answer")

    assert result.final_text == "done"
    assert (workspace.root / "answer.txt").read_text() == "42"
    assert store.load(session.id) is not None
    trace_text = (tmp_path / "trace.jsonl").read_text()
    assert '"model_call"' in trace_text
    assert '"tool_call"' in trace_text
    audit_text = (tmp_path / "audit.jsonl").read_text()
    assert '"action": "write_file"' in audit_text


def test_kernel_stops_on_final_answer_without_tools(tmp_path: Path) -> None:
    model = FakeModelClient([ModelResponse(content="plain answer")])
    session = Session.new(workspace=str(tmp_path))
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=Workspace(tmp_path),
        policy=Policy(PermissionMode.READ_ONLY),
    )

    result = kernel.run_turn(session, "hi")

    assert result.final_text == "plain answer"
    assert result.iterations == 1


def test_kernel_handles_unknown_tool_as_recoverable_tool_error(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    model = FakeModelClient(
        [
            ModelResponse(
                content="calling bad tool",
                tool_calls=[ToolCall(id="call-1", name="missing_tool", arguments={})],
            ),
            ModelResponse(content="I saw the tool error."),
        ]
    )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
        trace=trace,
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "use bad tool")

    assert result.stop_reason == "final_answer"
    assert "tool_error" in (tmp_path / "trace.jsonl").read_text()


def test_kernel_records_model_error_and_returns_failure(tmp_path: Path) -> None:
    class BrokenModel(FakeModelClient):
        def generate(self, messages, tools):  # noqa: ANN001
            raise RuntimeError("model down")

    workspace = Workspace(tmp_path / "ws")
    kernel = AgentKernel(
        model=BrokenModel([]),
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
        trace=TraceRecorder(tmp_path / "trace.jsonl"),
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "hi")

    assert result.stop_reason == "model_error"
    assert "model down" in result.final_text
    assert '"model_error"' in (tmp_path / "trace.jsonl").read_text()


def test_kernel_policy_denies_disallowed_tool_and_audits(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    audit = AuditLog(tmp_path / "audit.jsonl")
    model = FakeModelClient(
        [
            ModelResponse(
                content="try write",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="write_file",
                        arguments={"path": "nope.txt", "content": "bad"},
                    )
                ],
            ),
            ModelResponse(content="tool was denied"),
        ]
    )
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.DANGER, allowed_tools={"read_file"}, audit=audit),
        audit=audit,
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "write")

    assert result.stop_reason == "final_answer"
    assert not (workspace.root / "nope.txt").exists()
    events = audit.read_events()
    assert any(event["type"] == "policy_denial" for event in events)
    assert any(event["type"] == "tool_call" and event["allowed"] is False for event in events)
