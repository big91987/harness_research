from pathlib import Path

from harness.handoff import HandoffBuilder
from harness.schema import Message
from harness.session import Session
from harness.tasks import TaskStore
from harness.trace import TraceRecorder


def test_handoff_builder_renders_task_session_and_recent_messages(tmp_path: Path) -> None:
    task_store = TaskStore(tmp_path / "tasks")
    task = task_store.create("ship harness", description="make local harness usable")
    session = Session.new(workspace=str(tmp_path / "ws"))
    session.metadata["task_id"] = task.id
    session.usage["total_tokens"] = 42
    session.cost_usd = 0.01
    session.messages.append(Message.user("continue work"))
    session.messages.append(Message.assistant("checkpoint complete"))
    task_store.update(task.id, session_id=session.id)
    trace = TraceRecorder(tmp_path / "trace.jsonl")
    trace.record("model_call", session_id=session.id)
    trace.record("turn_end", session_id=session.id, stop_reason="final_answer", final_text="checkpoint complete")

    text = HandoffBuilder().render(
        session=session,
        task=task_store.load(task.id),
        trace_summary=trace.summary(),
    )

    assert "# Harness Handoff" in text
    assert "ship harness" in text
    assert session.id in text
    assert "total_tokens: 42" in text
    assert "user: continue work" in text
    assert "assistant: checkpoint complete" in text
