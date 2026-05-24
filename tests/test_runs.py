import os
import subprocess
import sys
from pathlib import Path

from harness.runs import RunStatus, RunStore


def test_run_store_creates_finishes_lists_and_filters(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    first = store.create(prompt="one", workspace="/ws")
    second = store.create(prompt="two", workspace="/ws", session_id="s2", task_id="task-1")

    finished = store.finish(
        second.id,
        status=RunStatus.SUCCEEDED,
        session_id="s2",
        turn_id="t2",
        stop_reason="final_answer",
        iterations=2,
    )

    assert first.status == RunStatus.IN_PROGRESS.value
    assert finished.status == RunStatus.SUCCEEDED.value
    assert finished.ended_at is not None
    assert store.load(second.id).turn_id == "t2"
    assert [record.id for record in store.list(status=RunStatus.SUCCEEDED)] == [second.id]
    assert [record.id for record in store.list(session_id="s2")] == [second.id]


def test_run_store_enqueues_starts_and_cancels_runs(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    pending = store.enqueue(prompt="queued", workspace="/ws", session_id="existing-session", task_id="task-1")

    started = store.start(pending.id, session_id="s1")

    assert pending.status == RunStatus.PENDING.value
    assert pending.session_id == "existing-session"
    assert started.status == RunStatus.IN_PROGRESS.value
    assert started.session_id == "s1"

    cancelled = store.cancel(started.id, reason="user request")

    assert cancelled.status == RunStatus.CANCELLED.value
    assert cancelled.stop_reason == "cancelled"
    assert cancelled.metadata["cancel_reason"] == "user request"
    assert [record.id for record in store.list(status=RunStatus.CANCELLED)] == [pending.id]


def test_run_store_refuses_to_cancel_finished_runs(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    record = store.create(prompt="done", workspace="/ws", session_id="s1")
    store.finish(
        record.id,
        status=RunStatus.SUCCEEDED,
        session_id="s1",
        turn_id="t1",
        stop_reason="final_answer",
        iterations=1,
    )

    try:
        store.cancel(record.id)
    except ValueError as exc:
        assert "cannot be cancelled" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_store_serializes_concurrent_creates(tmp_path: Path) -> None:
    script = """
from harness.runs import RunStore
import sys

RunStore(sys.argv[1]).create(prompt=sys.argv[2], workspace=sys.argv[3])
"""

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), f"prompt-{index}", "/ws"],
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

    prompts = {record.prompt for record in RunStore(tmp_path).list()}

    assert prompts == {f"prompt-{index}" for index in range(8)}
