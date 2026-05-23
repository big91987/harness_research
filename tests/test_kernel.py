from pathlib import Path

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
    )

    session = Session.new(workspace=str(workspace.root))
    result = kernel.run_turn(session, "create answer")

    assert result.final_text == "done"
    assert (workspace.root / "answer.txt").read_text() == "42"
    assert store.load(session.id) is not None
    trace_text = (tmp_path / "trace.jsonl").read_text()
    assert '"model_call"' in trace_text
    assert '"tool_call"' in trace_text


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

