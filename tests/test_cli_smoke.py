import subprocess
import sys
import os
import json
from pathlib import Path


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
    assert "last_assistant: two" in show.stdout
