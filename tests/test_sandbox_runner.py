import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="sandbox runner uses macOS sandbox-exec in Phase 1",
)


def _run_runner(request: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "harness.sandbox_runner"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src", "HARNESS_TEST_SECRET": "leak-me"},
        check=False,
    )


def test_sandbox_runner_runs_bash_inside_workspace(tmp_path: Path) -> None:
    request = {
        "tool": "bash",
        "workspace_root": str(tmp_path),
        "cwd": str(tmp_path),
        "command": "printf ok > out.txt && cat out.txt",
        "timeout_seconds": 5,
    }

    result = _run_runner(request)

    assert result.returncode == 0
    assert result.stdout == "ok"
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "ok"


def test_sandbox_runner_rejects_cwd_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent
    request = {
        "tool": "bash",
        "workspace_root": str(tmp_path),
        "cwd": str(outside),
        "command": "pwd",
        "timeout_seconds": 5,
    }

    result = _run_runner(request)

    assert result.returncode == 2
    assert "cwd escapes workspace" in result.stderr


def test_sandbox_runner_scrubs_parent_environment(tmp_path: Path) -> None:
    request = {
        "tool": "bash",
        "workspace_root": str(tmp_path),
        "cwd": str(tmp_path),
        "command": "printf \"${HARNESS_TEST_SECRET:-missing}\"",
        "timeout_seconds": 5,
    }

    result = _run_runner(request)

    assert result.returncode == 0
    assert result.stdout == "missing"


def test_sandbox_runner_accepts_explicit_environment(tmp_path: Path) -> None:
    request = {
        "tool": "bash",
        "workspace_root": str(tmp_path),
        "cwd": str(tmp_path),
        "command": "printf \"$HARNESS_EXPLICIT\"",
        "env": {"HARNESS_EXPLICIT": "allowed"},
        "timeout_seconds": 5,
    }

    result = _run_runner(request)

    assert result.returncode == 0
    assert result.stdout == "allowed"


def test_sandbox_runner_rejects_writes_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.unlink(missing_ok=True)
    request = {
        "tool": "bash",
        "workspace_root": str(tmp_path),
        "cwd": str(tmp_path),
        "command": f"printf ok > inside.txt && printf bad > {outside}",
        "timeout_seconds": 5,
    }

    result = _run_runner(request)

    if platform.system() == "Darwin":
        assert result.returncode != 0
        assert "Operation not permitted" in result.stderr
        assert not outside.exists()
        assert (tmp_path / "inside.txt").read_text(encoding="utf-8") == "ok"
    else:
        assert result.returncode == 2
        assert "macOS sandbox-exec is required" in result.stderr
        assert not outside.exists()


def test_sandbox_runner_rejects_sensitive_host_reads(tmp_path: Path) -> None:
    request = {
        "tool": "bash",
        "workspace_root": str(tmp_path),
        "cwd": str(tmp_path),
        "command": "cat /etc/passwd",
        "timeout_seconds": 5,
    }

    result = _run_runner(request)

    assert result.returncode != 0
    assert "Operation not permitted" in result.stderr
