import subprocess
import sys
import os
import json
from pathlib import Path


def _write_mock_response(tmp_path: Path, responses: list[dict]) -> Path:
    path = tmp_path / "responses.json"
    path.write_text(json.dumps(responses), encoding="utf-8")
    return path


def test_cli_run_with_mock_final_answer(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    trace = tmp_path / "trace.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "say hi",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(trace),
            "--mock-final",
            "hi from harness",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "hi from harness" in result.stdout
    assert trace.exists()
    assert '"turn_end"' in trace.read_text()


def test_cli_run_with_mock_tool_script(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = tmp_path / "responses.json"
    script.write_text(
        json.dumps(
            [
                {
                    "content": "writing file",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "write_file",
                            "arguments": {"path": "out.txt", "content": "ok"},
                        }
                    ],
                },
                {"content": "created out.txt"},
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "create file",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--permission",
            "workspace-write",
            "--mock-responses",
            str(script),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "created out.txt" in result.stdout
    assert (workspace / "out.txt").read_text() == "ok"


def test_cli_run_uses_config_file(tmp_path: Path) -> None:
    config = tmp_path / "harness.json"
    config.write_text(
        json.dumps(
            {
                "workspace": str(tmp_path / "ws"),
                "session_dir": str(tmp_path / "sessions"),
                "trace": str(tmp_path / "trace.jsonl"),
                "memory_dir": str(tmp_path / "memory"),
                "permission": "read-only",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--config",
            str(config),
            "run",
            "say hi",
            "--mock-final",
            "configured",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "configured" in result.stdout
    assert (tmp_path / "trace.jsonl").exists()


def test_cli_can_resume_existing_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "ws"
    env = {**os.environ, "PYTHONPATH": "src"}

    first = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "first",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(session_dir),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--mock-final",
            "one",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    session_line = [line for line in first.stdout.splitlines() if line.startswith("session:")][0]
    session_id = session_line.split(":", 1)[1].strip()

    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "second",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(session_dir),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--session",
            session_id,
            "--mock-final",
            "two",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "two" in second.stdout

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "sessions",
            "--session-dir",
            str(session_dir),
            "--show",
            session_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "messages: 4" in show.stdout
    assert "usage_total_tokens:" in show.stdout
    assert "cost_usd:" in show.stdout
    assert "last_assistant: two" in show.stdout


def test_cli_skills_add_search_and_render(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    skill_dir = tmp_path / "skills"

    add = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "skills",
            "--skill-dir",
            str(skill_dir),
            "--add",
            "pytest-debug",
            "--description",
            "Debug Python tests",
            "--body",
            "Run pytest -q before broad checks.",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "added: pytest-debug" in add.stdout

    search = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "skills",
            "--skill-dir",
            str(skill_dir),
            "--search",
            "python",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "pytest-debug: Debug Python tests" in search.stdout

    render = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "skills",
            "--skill-dir",
            str(skill_dir),
            "--query",
            "debug python",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "Available skills:" in render.stdout


def test_cli_tasks_create_update_show_and_associate_run(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    task_dir = tmp_path / "tasks"

    created = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--add",
            "ship harness",
            "--description",
            "local harness task",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    task_id = [line for line in created.stdout.splitlines() if line.startswith("task:")][0].split(":", 1)[1].strip()

    updated = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--update",
            task_id,
            "--status",
            "in_progress",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "status: in_progress" in updated.stdout

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "work task",
            "--workspace",
            str(tmp_path / "ws"),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--task-dir",
            str(task_dir),
            "--task-id",
            task_id,
            "--mock-final",
            "done-ish",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    session_id = [line for line in run.stdout.splitlines() if line.startswith("session:")][0].split(":", 1)[1].strip()

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--show",
            task_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "ship harness" in show.stdout
    assert "status: done" in show.stdout
    assert f"session: {session_id}" in show.stdout


def test_cli_run_marks_task_blocked_on_failed_turn(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    task_dir = tmp_path / "tasks"
    created = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--add",
            "blocked task",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    task_id = [line for line in created.stdout.splitlines() if line.startswith("task:")][0].split(":", 1)[1].strip()

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "over budget",
            "--workspace",
            str(tmp_path / "ws"),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--task-dir",
            str(task_dir),
            "--task-id",
            task_id,
            "--max-total-tokens",
            "0",
            "--mock-responses",
            str(_write_mock_response(tmp_path, [{"content": "too much", "usage": {"total_tokens": 1}}])),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert run.returncode == 2

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--show",
            task_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "status: blocked" in show.stdout


def test_cli_handoff_renders_session_summary(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    session_dir = tmp_path / "sessions"
    task_dir = tmp_path / "tasks"
    task = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--add",
            "handoff task",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    task_id = [line for line in task.stdout.splitlines() if line.startswith("task:")][0].split(":", 1)[1].strip()
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "make handoff",
            "--workspace",
            str(tmp_path / "ws"),
            "--session-dir",
            str(session_dir),
            "--task-dir",
            str(task_dir),
            "--task-id",
            task_id,
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--mock-final",
            "handoff ready",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    session_id = [line for line in run.stdout.splitlines() if line.startswith("session:")][0].split(":", 1)[1].strip()

    handoff = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "handoff",
            "--session-dir",
            str(session_dir),
            "--task-dir",
            str(task_dir),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--session",
            session_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert "# Harness Handoff" in handoff.stdout
    assert "handoff task" in handoff.stdout
    assert "handoff ready" in handoff.stdout
