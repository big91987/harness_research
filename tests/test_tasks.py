from pathlib import Path
import os
import subprocess
import sys

from harness.tasks import TaskStatus, TaskStore


def test_task_store_creates_updates_lists_and_shows_tasks(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)

    task = store.create("ship harness", description="make local harness usable")
    updated = store.update(task.id, status=TaskStatus.IN_PROGRESS, session_id="s1")

    assert updated.status == TaskStatus.IN_PROGRESS.value
    assert updated.session_id == "s1"
    assert store.load(task.id).title == "ship harness"
    assert [item.id for item in store.list()] == [task.id]
    history = store.history(task.id)
    assert [event["type"] for event in history] == ["created", "updated"]
    assert history[1]["changes"]["status"] == TaskStatus.IN_PROGRESS.value
    assert history[1]["changes"]["session_id"] == "s1"


def test_task_store_filters_by_status(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    first = store.create("one")
    second = store.create("two")
    store.update(second.id, status=TaskStatus.DONE)

    done = store.list(status=TaskStatus.DONE)

    assert [task.id for task in done] == [second.id]
    assert store.load(first.id).status == TaskStatus.TODO.value


def test_task_store_filters_by_session_and_deletes(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    first = store.create("one")
    second = store.create("two")
    store.update(first.id, session_id="s1")
    store.update(second.id, session_id="s2")

    assert [task.id for task in store.list(session_id="s1")] == [first.id]
    assert store.delete(first.id)
    assert store.list(session_id="s1") == []
    assert not store.delete(first.id)


def test_task_store_renders_task_context(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    task = store.create("ship harness", description="make local harness usable")
    store.update(task.id, status=TaskStatus.IN_PROGRESS, session_id="s1")

    context = store.render_context(task.id)

    assert "Active task:" in context
    assert "ship harness" in context
    assert "make local harness usable" in context
    assert "in_progress" in context
    assert "s1" in context


def test_task_store_merges_metadata_on_update(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    task = store.create("ship harness", metadata={"owner": "agent"})

    updated = store.update(task.id, metadata={"last_stop_reason": "final_answer"})

    assert updated.metadata == {
        "owner": "agent",
        "last_stop_reason": "final_answer",
    }
    history = store.history(task.id)
    assert history[-1]["changes"]["metadata"] == {"last_stop_reason": "final_answer"}


def test_task_store_history_survives_reload(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    task = store.create("ship harness")
    store.update(task.id, status=TaskStatus.BLOCKED, metadata={"reason": "budget"})

    reloaded = TaskStore(tmp_path)
    history = reloaded.history(task.id)

    assert len(history) == 2
    assert history[0]["type"] == "created"
    assert history[1]["changes"]["status"] == "blocked"


def test_task_store_serializes_concurrent_updates(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    task = store.create("ship harness")
    script = """
from harness.tasks import TaskStore
import sys

store = TaskStore(sys.argv[1])
store.update(sys.argv[2], metadata={sys.argv[3]: sys.argv[4]})
"""

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), task.id, f"k{index}", f"v{index}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        for index in range(8)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stdout + stderr

    updated = store.load(task.id)

    assert updated.metadata == {f"k{index}": f"v{index}" for index in range(8)}
    assert len([event for event in updated.history if event["type"] == "updated"]) == 8
