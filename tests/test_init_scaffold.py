import json
import os
import subprocess
import sys
from pathlib import Path

from harness.scaffold import scaffold_project


def test_scaffold_project_writes_config_and_samples(tmp_path: Path) -> None:
    result = scaffold_project(tmp_path)

    assert result.config_path.exists()
    assert result.mock_responses_path.exists()
    assert result.golden_path.exists()
    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    assert config["workspace"].endswith("workspace")
    assert config["skill_dir"].endswith("skills")
    responses = json.loads(result.mock_responses_path.read_text(encoding="utf-8"))
    assert responses[0]["tool_calls"][0]["name"] == "write_file"


def test_cli_init_outputs_runnable_project(tmp_path: Path) -> None:
    init = subprocess.run(
        [sys.executable, "-m", "harness.cli", "init", "--root", str(tmp_path)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "config:" in init.stdout

    config_path = tmp_path / "harness.json"
    responses_path = tmp_path / "samples" / "mock_responses.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--config",
            str(config_path),
            "run",
            "create sample",
            "--mock-responses",
            str(responses_path),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "created sample.txt" in run.stdout
    assert (tmp_path / "workspace" / "sample.txt").read_text(encoding="utf-8") == "hello from harness"
