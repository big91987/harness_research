import json
import os
import subprocess
import sys
from pathlib import Path

from harness.artifacts import ArtifactStore
from harness.audit import AuditLog


def test_artifact_store_registers_and_verifies_workspace_file(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    artifact_file = workspace / "result.txt"
    artifact_file.write_text("hello", encoding="utf-8")
    store = ArtifactStore(tmp_path / "artifacts")

    artifact = store.register_file(artifact_file, workspace_root=workspace, kind="output")

    assert artifact.relative_path == "result.txt"
    assert artifact.size == 5
    assert store.verify(artifact.id)
    artifact_file.write_text("changed", encoding="utf-8")
    assert not store.verify(artifact.id)


def test_audit_log_records_jsonl_events(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")

    audit.record("tool_call", session_id="s1", actor="agent", action="write_file", allowed=True)
    audit.record("approval", session_id="s1", actor="user", action="bash", allowed=False)

    events = audit.read_events()
    assert [event["type"] for event in events] == ["tool_call", "approval"]
    assert events[1]["allowed"] is False


def test_cli_artifacts_and_audit_smoke(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "out.txt").write_text("ok", encoding="utf-8")

    register = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "artifacts",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--workspace",
            str(workspace),
            "--register",
            str(workspace / "out.txt"),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "artifact:" in register.stdout
    artifact_id = register.stdout.splitlines()[0].split(":", 1)[1].strip()

    listing = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "artifacts",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--verify",
            artifact_id,
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "verified: True" in listing.stdout

    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(json.dumps({"type": "tool_call", "action": "read_file"}) + "\n", encoding="utf-8")
    audit = subprocess.run(
        [sys.executable, "-m", "harness.cli", "audit", "--audit", str(audit_path)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "tool_call read_file" in audit.stdout

