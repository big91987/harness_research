from pathlib import Path

from harness.context import ContextManager
from harness.schema import Message
from harness.session import JsonlSessionStore, Session, SessionBundle


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


def test_session_bundle_exports_and_imports_session(tmp_path: Path) -> None:
    source = JsonlSessionStore(tmp_path / "source")
    target = JsonlSessionStore(tmp_path / "target")
    session = Session.new(workspace=str(tmp_path / "ws"))
    session.messages.append(Message.user("hello"))
    source.save(session)
    bundle_path = tmp_path / "session.json"

    SessionBundle.export(source.load(session.id), bundle_path)
    imported = SessionBundle.import_into(bundle_path, target)

    assert imported.id == session.id
    assert target.load(session.id).messages[0].content == "hello"


def test_session_store_lists_summaries_and_filters_by_workspace(tmp_path: Path) -> None:
    store = JsonlSessionStore(tmp_path)
    first = Session.new(workspace="/workspace/one")
    first.messages.append(Message.user("hello"))
    first.messages.append(Message.assistant("done"))
    first.usage["total_tokens"] = 5
    first.cost_usd = 0.001
    second = Session.new(workspace="/workspace/two")
    second.messages.append(Message.user("other"))
    store.save(first)
    store.save(second)

    summaries = store.summaries(workspace_contains="one")

    assert len(summaries) == 1
    assert summaries[0]["id"] == first.id
    assert summaries[0]["workspace"] == "/workspace/one"
    assert summaries[0]["messages"] == 2
    assert summaries[0]["usage_total_tokens"] == 5
    assert summaries[0]["cost_usd"] == 0.001
    assert summaries[0]["last_role"] == "assistant"
    assert summaries[0]["last_content"] == "done"


def test_context_manager_compacts_middle_messages() -> None:
    messages = [Message.user(f"msg {i}") for i in range(12)]
    manager = ContextManager(max_messages=6, keep_head=1, keep_tail=3)

    compacted = manager.prepare(messages)

    assert len(compacted) == 5
    assert compacted[0].content == "msg 0"
    assert "Compacted conversation summary" in compacted[1].content
    assert [m.content for m in compacted[-3:]] == ["msg 9", "msg 10", "msg 11"]


def test_context_manager_compact_returns_stats_and_metadata() -> None:
    messages = [Message.user(f"msg {i}") for i in range(10)]
    manager = ContextManager(max_messages=5, keep_head=1, keep_tail=2)

    result = manager.compact(messages)

    assert result.original_count == 10
    assert result.dropped_count == 7
    assert len(result.messages) == 4
    summary = result.messages[1]
    assert summary.role == "system"
    assert summary.metadata["kind"] == "compaction_summary"
    assert summary.metadata["dropped_messages"] == 7
    assert "user: msg 1" in summary.content
