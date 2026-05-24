import json
import os
import subprocess
import sys
from pathlib import Path

from harness.artifacts import ArtifactQuery, ArtifactStore
from harness.audit import AuditLog, AuditQuery


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


def test_artifact_query_filters_by_kind_path_and_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "result.txt").write_text("hello", encoding="utf-8")
    (workspace / "checkpoint.json").write_text("{}", encoding="utf-8")
    store = ArtifactStore(tmp_path / "artifacts")
    store.register_file(workspace / "result.txt", workspace_root=workspace, kind="output")
    store.register_file(workspace / "checkpoint.json", workspace_root=workspace, kind="checkpoint-manifest")

    artifacts = ArtifactQuery(store).artifacts(kind="checkpoint-manifest", path_contains="checkpoint", limit=1)

    assert len(artifacts) == 1
    assert artifacts[0].relative_path == "checkpoint.json"


def test_artifact_store_verify_all_reports_changed_and_missing(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ok_file = workspace / "ok.txt"
    changed_file = workspace / "changed.txt"
    missing_file = workspace / "missing.txt"
    ok_file.write_text("ok", encoding="utf-8")
    changed_file.write_text("before", encoding="utf-8")
    missing_file.write_text("gone", encoding="utf-8")
    store = ArtifactStore(tmp_path / "artifacts")
    ok_artifact = store.register_file(ok_file, workspace_root=workspace)
    changed_artifact = store.register_file(changed_file, workspace_root=workspace)
    missing_artifact = store.register_file(missing_file, workspace_root=workspace)
    changed_file.write_text("after", encoding="utf-8")
    missing_file.unlink()

    report = store.verify_all()

    by_id = {item["id"]: item for item in report}
    assert by_id[ok_artifact.id]["status"] == "ok"
    assert by_id[changed_artifact.id]["status"] == "changed"
    assert by_id[missing_artifact.id]["status"] == "missing"


def test_audit_log_records_jsonl_events(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")

    audit.record("tool_call", session_id="s1", actor="agent", action="write_file", allowed=True)
    audit.record("approval", session_id="s1", actor="user", action="bash", allowed=False)

    events = audit.read_events()
    assert [event["type"] for event in events] == ["tool_call", "approval"]
    assert events[1]["allowed"] is False


def test_audit_log_serializes_concurrent_events(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    script = """
from harness.audit import AuditLog
import sys

AuditLog(sys.argv[1]).record("worker_event", action=sys.argv[2], allowed=True)
"""

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(audit), str(index)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        for index in range(12)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stdout + stderr

    events = AuditLog(audit).read_events()

    assert len(events) == 12
    assert {event["action"] for event in events} == {str(index) for index in range(12)}


def test_audit_query_filters_events(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.record("tool_call", session_id="s1", turn_id="t1", actor="agent", action="read_file", allowed=True)
    audit.record("tool_call", session_id="s2", turn_id="t1", actor="agent", action="bash", allowed=False)
    audit.record("approval", session_id="s2", turn_id="t2", actor="user", action="bash", allowed=False)

    events = AuditQuery(audit).events(session_id="s2", turn_id="t2", action="bash", allowed=False, limit=1)

    assert len(events) == 1
    assert events[0]["type"] == "approval"
    assert events[0]["session_id"] == "s2"
    assert events[0]["turn_id"] == "t2"


def test_audit_query_summarizes_events(tmp_path: Path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.record("tool_call", session_id="s1", actor="agent", action="read_file", allowed=True)
    audit.record("tool_call", session_id="s1", actor="agent", action="bash", allowed=False)
    audit.record("approval", actor="user", action="bash", allowed=False)
    audit.record("policy_denial", actor="policy", action="write_file", allowed=False)

    summary = AuditQuery(audit).summary()

    assert summary["events"] == 4
    assert summary["allowed"] == 1
    assert summary["denied"] == 3
    assert summary["by_type"] == {"approval": 1, "policy_denial": 1, "tool_call": 2}
    assert summary["by_action"]["bash"] == 2


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

    artifact_json = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "artifacts",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--kind",
            "file",
            "--path-contains",
            "out",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert '"relative_path": "out.txt"' in artifact_json.stdout

    (workspace / "out.txt").write_text("changed", encoding="utf-8")
    verify_all = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "artifacts",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--verify-all",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert '"status": "changed"' in verify_all.stdout

    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        json.dumps({"type": "tool_call", "action": "read_file", "turn_id": "t1"}) + "\n"
        + json.dumps({"type": "tool_call", "action": "bash", "turn_id": "t2"}) + "\n",
        encoding="utf-8",
    )
    audit = subprocess.run(
        [sys.executable, "-m", "harness.cli", "audit", "--audit", str(audit_path)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "tool_call read_file" in audit.stdout

    audit_json = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "audit",
            "--audit",
            str(audit_path),
            "--type",
            "tool_call",
            "--turn",
            "t1",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert '"type": "tool_call"' in audit_json.stdout
    assert '"turn_id": "t1"' in audit_json.stdout
    assert '"turn_id": "t2"' not in audit_json.stdout


def test_cli_audit_summary(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLog(audit_path)
    audit.record("tool_call", session_id="s1", actor="agent", action="read_file", allowed=True)
    audit.record("policy_denial", actor="policy", action="bash", allowed=False)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "audit",
            "--audit",
            str(audit_path),
            "--summary",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "events: 2" in result.stdout
    assert "denied: 1" in result.stdout
    assert "action.bash: 1" in result.stdout
