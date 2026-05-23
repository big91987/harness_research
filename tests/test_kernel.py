from pathlib import Path

from harness.audit import AuditLog
from harness.cost import ModelPricing, RuntimeBudget
from harness.hooks import HookResult
from harness.kernel import AgentKernel
from harness.model import FakeModelClient
from harness.permissions import PermissionMode, Policy
from harness.schema import ModelResponse, ToolCall
from harness.session import JsonlSessionStore, Session
from harness.skills import SkillStore
from harness.tools import default_tool_registry
from harness.trace import TraceRecorder
from harness.workspace import Workspace


class RecordingHooks:
    def __init__(self) -> None:
        self.events = []

    def run(self, event_type, payload):  # noqa: ANN001
        self.events.append((event_type, payload))
        return [HookResult(event=event_type, command=["record"], returncode=0, stdout="", stderr="")]


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
    assert session.usage["prompt_tokens"] == 0
    assert session.usage["total_tokens"] == 0
    assert (workspace.root / "answer.txt").read_text() == "42"
    assert store.load(session.id) is not None
    trace_text = (tmp_path / "trace.jsonl").read_text()
    assert '"model_call"' in trace_text
    assert '"tool_call"' in trace_text
    audit_text = (tmp_path / "audit.jsonl").read_text()
    assert '"action": "write_file"' in audit_text


def test_kernel_emits_lifecycle_hooks(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    hooks = RecordingHooks()
    kernel = AgentKernel(
        model=FakeModelClient([ModelResponse(content="ok")]),
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
        hooks=hooks,
        trace=TraceRecorder(tmp_path / "trace.jsonl"),
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "hi")

    assert result.stop_reason == "final_answer"
    event_types = [event_type for event_type, _ in hooks.events]
    assert event_types == ["turn_start", "turn_end"]
    assert hooks.events[-1][1]["stop_reason"] == "final_answer"
    assert '"hook_result"' in (tmp_path / "trace.jsonl").read_text()


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


def test_kernel_aggregates_usage(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    model = FakeModelClient(
        [
            ModelResponse(
                content="tracked",
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
        ]
    )
    session = Session.new(workspace=str(workspace.root))
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
    )

    result = kernel.run_turn(session, "usage")

    assert result.stop_reason == "final_answer"
    assert session.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_kernel_aggregates_usage_aliases_and_cost(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    model = FakeModelClient(
        [
            ModelResponse(
                content="tracked",
                usage={"input_tokens": 1_000_000, "output_tokens": 500_000},
            )
        ]
    )
    session = Session.new(workspace=str(workspace.root))
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
        trace=trace,
        pricing=ModelPricing(input_cost_per_million_tokens=1.0, output_cost_per_million_tokens=2.0),
    )

    result = kernel.run_turn(session, "usage")

    assert result.stop_reason == "final_answer"
    assert session.usage == {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 500_000,
        "total_tokens": 1_500_000,
    }
    assert session.cost_usd == 2.0
    assert '"cost_usd": 2.0' in (tmp_path / "trace.jsonl").read_text()


def test_kernel_stops_before_tools_when_runtime_budget_is_exceeded(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "ws")
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    model = FakeModelClient(
        [
            ModelResponse(
                content="would write",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="write_file",
                        arguments={"path": "over.txt", "content": "too much"},
                    )
                ],
                usage={"prompt_tokens": 101, "completion_tokens": 0, "total_tokens": 101},
            )
        ]
    )
    session = Session.new(workspace=str(workspace.root))
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.WORKSPACE_WRITE),
        trace=trace,
        budget=RuntimeBudget(max_total_tokens=100),
    )

    result = kernel.run_turn(session, "write over budget")

    assert result.stop_reason == "budget_exceeded"
    assert "Budget exceeded" in result.final_text
    assert not (workspace.root / "over.txt").exists()
    trace_text = (tmp_path / "trace.jsonl").read_text()
    assert '"budget_exceeded"' in trace_text
    assert '"tool_call"' not in trace_text


def test_kernel_injects_relevant_skill_context(tmp_path: Path) -> None:
    class CapturingModel(FakeModelClient):
        captured = []

        def generate(self, messages, tools):  # noqa: ANN001
            self.captured = messages
            return super().generate(messages, tools)

    workspace = Workspace(tmp_path / "ws")
    skills = SkillStore(tmp_path / "skills")
    skills.add("pytest-debug", "Run focused pytest checks first.", description="Debug Python tests")
    model = CapturingModel([ModelResponse(content="ok")])
    kernel = AgentKernel(
        model=model,
        tools=default_tool_registry(),
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.READ_ONLY),
        skills=skills,
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "debug python tests")

    assert result.stop_reason == "final_answer"
    system_text = "\n".join(message.content for message in model.captured if message.role == "system")
    assert "Available skills:" in system_text
    assert "pytest-debug" in system_text


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
