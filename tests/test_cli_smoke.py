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
