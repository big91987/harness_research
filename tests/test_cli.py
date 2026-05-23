from pathlib import Path
import subprocess
import sys
import os

from harness.cli import build_parser


def test_cli_parser_accepts_run_options(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "hello",
            "--workspace",
            str(tmp_path),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--model",
            "test-model",
            "--model-timeout-seconds",
            "7",
            "--sandbox-runner",
            "python3 /tmp/runner.py",
            "--base-url",
            "https://example.com",
        ]
    )

    assert args.command == "run"
    assert args.prompt == "hello"
    assert args.workspace == str(tmp_path)
    assert args.model_timeout_seconds == 7
    assert args.sandbox_runner == "python3 /tmp/runner.py"


def test_cli_tools_can_show_schema_and_emit_json() -> None:
    env = {**os.environ, "PYTHONPATH": "src"}

    shown = subprocess.run(
        [sys.executable, "-m", "harness.cli", "tools", "--show", "read_file"],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert "name: read_file" in shown.stdout
    assert "required_permission: read-only" in shown.stdout
    assert "category: filesystem" in shown.stdout

    json_result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "tools", "--json"],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )
    assert '"name": "read_file"' in json_result.stdout
    assert '"parameters"' in json_result.stdout
