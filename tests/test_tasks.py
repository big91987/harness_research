from pathlib import Path

from harness.tasks import TaskStatus, TaskStore


def test_task_store_creates_updates_lists_and_shows_tasks(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)

    task = store.create("ship harness", description="make local harness usable")
    updated = store.update(task.id, status=TaskStatus.IN_PROGRESS, session_id="s1")

    assert updated.status == TaskStatus.IN_PROGRESS.value
    assert updated.session_id == "s1"
    assert store.load(task.id).title == "ship harness"
    assert [item.id for item in store.list()] == [task.id]


def test_task_store_filters_by_status(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    first = store.create("one")
    second = store.create("two")
    store.update(second.id, status=TaskStatus.DONE)

    done = store.list(status=TaskStatus.DONE)

    assert [task.id for task in done] == [second.id]
    assert store.load(first.id).status == TaskStatus.TODO.value
