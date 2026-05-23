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
