from pathlib import Path

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

