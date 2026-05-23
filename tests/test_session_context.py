from pathlib import Path

from harness.context import ContextManager
from harness.schema import Message
from harness.session import JsonlSessionStore, Session


def test_jsonl_session_store_round_trips_messages(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path)
    session = Session.new(workspace=str(tmp_path / "ws"))
    session.messages.append(Message.user("hello"))
    session.messages.append(Message.assistant("world"))

    store.save(session)
    loaded = store.load(session.id)

    assert loaded is not None
    assert loaded.id == session.id
    assert [m.content for m in loaded.messages] == ["hello", "world"]


def test_context_manager_compacts_middle_messages() -> None:
    messages = [Message.user(f"msg {i}") for i in range(12)]
    manager = ContextManager(max_messages=6, keep_head=1, keep_tail=3)

    compacted = manager.prepare(messages)

    assert len(compacted) == 5
    assert compacted[0].content == "msg 0"
    assert "Compacted conversation summary" in compacted[1].content
    assert [m.content for m in compacted[-3:]] == ["msg 9", "msg 10", "msg 11"]

