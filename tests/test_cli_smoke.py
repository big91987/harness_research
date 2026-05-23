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


def test_cli_run_can_emit_json_result(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "say hi",
            "--workspace",
            str(tmp_path / "workspace"),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--mock-final",
            "hi from harness",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    payload = json.loads(result.stdout)
    assert payload["final_text"] == "hi from harness"
    assert payload["stop_reason"] == "final_answer"
    assert payload["iterations"] == 1
    assert payload["session_id"]
    assert payload["turn_id"]


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


def test_cli_run_can_fail_fast_on_tool_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    script = _write_mock_response(
        tmp_path,
        [
            {
                "content": "try mixed tools",
                "tool_calls": [
                    {"id": "call-1", "name": "missing_tool", "arguments": {}},
                    {
                        "id": "call-2",
                        "name": "write_file",
                        "arguments": {"path": "should-not-exist.txt", "content": "bad"},
                    },
                ],
            },
            {"content": "saw failure"},
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "try mixed tools",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--permission",
            "workspace-write",
            "--fail-fast-on-tool-error",
            "--mock-responses",
            str(script),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "saw failure" in result.stdout
    assert not (workspace / "should-not-exist.txt").exists()
    assert '"tool_batch_aborted"' in (tmp_path / "trace.jsonl").read_text(encoding="utf-8")


def test_cli_run_can_restore_checkpoint_on_failure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("before", encoding="utf-8")
    script = _write_mock_response(
        tmp_path,
        [
            {
                "content": "writing risky change",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "write_file",
                        "arguments": {"path": "keep.txt", "content": "after"},
                    },
                    {
                        "id": "call-2",
                        "name": "write_file",
                        "arguments": {"path": "extra.txt", "content": "extra"},
                    },
                ],
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "risky edit",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--permission",
            "workspace-write",
            "--max-iterations",
            "1",
            "--checkpoint-before",
            "--checkpoint-dir",
            str(tmp_path / "checkpoints"),
            "--restore-checkpoint-on-failure",
            "--mock-responses",
            str(script),
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 2
    assert "checkpoint:" in result.stdout
    assert "restored_checkpoint:" in result.stdout
    assert "stop_reason: max_iterations" in result.stdout
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "before"
    assert not (workspace / "extra.txt").exists()


def test_cli_run_json_result_includes_checkpoint_restore(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("before", encoding="utf-8")
    script = _write_mock_response(
        tmp_path,
        [
            {
                "content": "writing risky change",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "write_file",
                        "arguments": {"path": "keep.txt", "content": "after"},
                    }
                ],
            }
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "risky edit",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--permission",
            "workspace-write",
            "--max-iterations",
            "1",
            "--checkpoint-before",
            "--checkpoint-dir",
            str(tmp_path / "checkpoints"),
            "--restore-checkpoint-on-failure",
            "--mock-responses",
            str(script),
            "--json",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["stop_reason"] == "max_iterations"
    assert payload["checkpoint_id"]
    assert payload["restored_checkpoint_id"] == payload["checkpoint_id"]
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "before"


def test_cli_run_records_checkpoint_lifecycle_in_trace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("before", encoding="utf-8")
    trace = tmp_path / "trace.jsonl"
    script = _write_mock_response(
        tmp_path,
        [
            {
                "content": "writing risky change",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "write_file",
                        "arguments": {"path": "keep.txt", "content": "after"},
                    }
                ],
            }
        ],
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "risky edit",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(trace),
            "--permission",
            "workspace-write",
            "--max-iterations",
            "1",
            "--checkpoint-before",
            "--checkpoint-dir",
            str(tmp_path / "checkpoints"),
            "--restore-checkpoint-on-failure",
            "--mock-responses",
            str(script),
            "--json",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    created = [event for event in events if event["type"] == "checkpoint_created"]
    restored = [event for event in events if event["type"] == "checkpoint_restored"]
    assert created[0]["checkpoint_id"]
    assert created[0]["manifest_path"].endswith("manifest.json")
    assert restored[0]["checkpoint_id"] == created[0]["checkpoint_id"]
    assert restored[0]["stop_reason"] == "max_iterations"


def test_cli_run_keeps_changes_after_successful_checkpointed_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keep.txt").write_text("before", encoding="utf-8")
    script = _write_mock_response(
        tmp_path,
        [
            {
                "content": "writing change",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "write_file",
                        "arguments": {"path": "keep.txt", "content": "after"},
                    }
                ],
            },
            {"content": "done"},
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "safe edit",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--permission",
            "workspace-write",
            "--checkpoint-before",
            "--checkpoint-dir",
            str(tmp_path / "checkpoints"),
            "--restore-checkpoint-on-failure",
            "--mock-responses",
            str(script),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "checkpoint:" in result.stdout
    assert "restored_checkpoint:" not in result.stdout
    assert "stop_reason: final_answer" in result.stdout
    assert (workspace / "keep.txt").read_text(encoding="utf-8") == "after"


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


def test_cli_config_show_redacts_api_key(tmp_path: Path) -> None:
    config = tmp_path / "harness.json"
    config.write_text(
        json.dumps({"api_key": "secret-key", "base_url": "https://api.example.com"}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--config",
            str(config),
            "config",
            "--show",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    payload = json.loads(result.stdout)
    assert payload["config"]["api_key"] == "***"
    assert "secret-key" not in result.stdout


def test_cli_config_validate_exits_nonzero_for_errors(tmp_path: Path) -> None:
    config = tmp_path / "harness.json"
    config.write_text(
        json.dumps({"permission": "invalid", "max_iterations": 0}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--config",
            str(config),
            "config",
            "--validate",
            "--json",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["valid"] is False
    assert {issue["key"] for issue in payload["issues"] if issue["level"] == "error"} >= {
        "permission",
        "max_iterations",
    }


def test_cli_tools_can_call_tool_with_json_args(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tools",
            "--workspace",
            str(workspace),
            "--permission",
            "workspace-write",
            "--call",
            "write_file",
            "--args-json",
            json.dumps({"path": "out.txt", "content": "ok"}),
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    payload = json.loads(result.stdout)
    assert payload["name"] == "write_file"
    assert payload["is_error"] is False
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "ok"


def test_cli_tools_call_exits_nonzero_on_policy_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tools",
            "--workspace",
            str(tmp_path / "workspace"),
            "--permission",
            "read-only",
            "--call",
            "write_file",
            "--args-json",
            json.dumps({"path": "out.txt", "content": "no"}),
            "--json",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["is_error"] is True
    assert "requires workspace-write permission" in payload["output"]


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

    listing = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "sessions",
            "--session-dir",
            str(session_dir),
            "--workspace-contains",
            "ws",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert f'"id": "{session_id}"' in listing.stdout
    assert '"messages": 4' in listing.stdout


def test_cli_sessions_export_and_import(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "export me",
            "--workspace",
            str(tmp_path / "ws"),
            "--session-dir",
            str(source_dir),
            "--mock-final",
            "portable",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    session_id = [line for line in run.stdout.splitlines() if line.startswith("session:")][0].split(":", 1)[1].strip()
    bundle = tmp_path / "session.json"

    export = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "sessions",
            "--session-dir",
            str(source_dir),
            "--export",
            session_id,
            "--output",
            str(bundle),
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "exported:" in export.stdout

    imported = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "sessions",
            "--session-dir",
            str(target_dir),
            "--import",
            str(bundle),
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert f"imported: {session_id}" in imported.stdout

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "sessions",
            "--session-dir",
            str(target_dir),
            "--show",
            session_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "last_assistant: portable" in show.stdout


def test_cli_sessions_compact_persists_summary(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "ws"
    env = {**os.environ, "PYTHONPATH": "src"}

    first = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "seed",
            "--workspace",
            str(workspace),
            "--session-dir",
            str(session_dir),
            "--mock-final",
            "first",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    session_id = [line for line in first.stdout.splitlines() if line.startswith("session:")][0].split(":", 1)[1].strip()
    for index in range(6):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "harness.cli",
                "run",
                f"turn {index}",
                "--workspace",
                str(workspace),
                "--session-dir",
                str(session_dir),
                "--session",
                session_id,
                "--mock-final",
                f"answer {index}",
            ],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )

    compacted = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "sessions",
            "--session-dir",
            str(session_dir),
            "--compact",
            session_id,
            "--max-messages",
            "6",
            "--keep-head",
            "1",
            "--keep-tail",
            "3",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert "dropped_messages:" in compacted.stdout
    shown = subprocess.run(
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

    assert "messages: 5" in shown.stdout
    assert "last_assistant: answer 5" in shown.stdout


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

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "skills",
            "--skill-dir",
            str(skill_dir),
            "--show",
            "pytest-debug",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "Run pytest -q" in show.stdout

    deleted = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "skills",
            "--skill-dir",
            str(skill_dir),
            "--delete",
            "pytest-debug",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "deleted: pytest-debug" in deleted.stdout


def test_cli_memory_list_and_clear(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": "src"}
    memory_dir = tmp_path / "memory"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "memory",
            "--memory-dir",
            str(memory_dir),
            "--add",
            "remember the kernel",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    listed = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "memory",
            "--memory-dir",
            str(memory_dir),
            "--list",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "- remember the kernel" in listed.stdout

    cleared = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "memory",
            "--memory-dir",
            str(memory_dir),
            "--clear",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "cleared" in cleared.stdout


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

    listed_json = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--session",
            session_id,
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert f'"id": "{task_id}"' in listed_json.stdout
    assert f'"session_id": "{session_id}"' in listed_json.stdout

    deleted = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "tasks",
            "--task-dir",
            str(task_dir),
            "--delete",
            task_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert f"deleted: {task_id}" in deleted.stdout


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
