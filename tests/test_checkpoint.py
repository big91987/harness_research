from pathlib import Path
import subprocess
import sys
import os

from harness.artifacts import ArtifactStore
from harness.checkpoint import WorkspaceCheckpoint


def test_workspace_checkpoint_creates_manifest_and_restores(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    (workspace / "nested").mkdir()
    (workspace / "nested" / "b.txt").write_text("beta", encoding="utf-8")

    checkpoint = WorkspaceCheckpoint.create(workspace, tmp_path / "checkpoints", label="before")

    assert checkpoint.label == "before"
    assert checkpoint.files["a.txt"].size == 5
    assert "nested/b.txt" in checkpoint.files

    (workspace / "a.txt").write_text("changed", encoding="utf-8")
    WorkspaceCheckpoint.restore(checkpoint.manifest_path, workspace)

    assert (workspace / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (workspace / "nested" / "b.txt").read_text(encoding="utf-8") == "beta"


def test_workspace_checkpoint_clean_restore_removes_extra_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    checkpoint = WorkspaceCheckpoint.create(workspace, tmp_path / "checkpoints")
    (workspace / "extra.txt").write_text("extra", encoding="utf-8")

    WorkspaceCheckpoint.restore(checkpoint.manifest_path, workspace, clean=True)

    assert (workspace / "a.txt").exists()
    assert not (workspace / "extra.txt").exists()


def test_workspace_checkpoint_diff_reports_added_modified_and_deleted(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "same.txt").write_text("same", encoding="utf-8")
    (workspace / "changed.txt").write_text("before", encoding="utf-8")
    (workspace / "deleted.txt").write_text("gone soon", encoding="utf-8")

    checkpoint = WorkspaceCheckpoint.create(workspace, tmp_path / "checkpoints")
    (workspace / "changed.txt").write_text("after", encoding="utf-8")
    (workspace / "deleted.txt").unlink()
    (workspace / "added.txt").write_text("new", encoding="utf-8")

    diff = WorkspaceCheckpoint.diff(checkpoint.manifest_path, workspace)

    assert diff.added == ["added.txt"]
    assert diff.modified == ["changed.txt"]
    assert diff.deleted == ["deleted.txt"]
    assert diff.unchanged == ["same.txt"]
    assert not diff.clean


def test_cli_checkpoint_can_register_manifest_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "checkpoint",
            "--workspace",
            str(workspace),
            "--checkpoint-dir",
            str(tmp_path / "checkpoints"),
            "--artifact-dir",
            str(artifact_dir),
            "--label",
            "before",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    artifact_id = [line for line in result.stdout.splitlines() if line.startswith("artifact:")][0].split(":", 1)[1].strip()
    artifact = ArtifactStore(artifact_dir).get(artifact_id)

    assert artifact is not None
    assert artifact.kind == "checkpoint-manifest"
    assert ArtifactStore(artifact_dir).verify(artifact_id)


def test_cli_checkpoint_diff(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    checkpoint = WorkspaceCheckpoint.create(workspace, tmp_path / "checkpoints")
    (workspace / "a.txt").write_text("changed", encoding="utf-8")
    (workspace / "b.txt").write_text("beta", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "checkpoint",
            "--workspace",
            str(workspace),
            "--diff",
            str(checkpoint.manifest_path),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "clean: False" in result.stdout
    assert "added: b.txt" in result.stdout
    assert "modified: a.txt" in result.stdout


def test_cli_checkpoint_clean_restore(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    checkpoint = WorkspaceCheckpoint.create(workspace, tmp_path / "checkpoints")
    (workspace / "extra.txt").write_text("extra", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "checkpoint",
            "--workspace",
            str(workspace),
            "--restore",
            str(checkpoint.manifest_path),
            "--clean",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "restored:" in result.stdout
    assert not (workspace / "extra.txt").exists()
