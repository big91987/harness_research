from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import uuid4


@dataclass(frozen=True)
class CheckpointFile:
    size: int
    sha256: str


@dataclass(frozen=True)
class WorkspaceDiff:
    added: list[str]
    modified: list[str]
    deleted: list[str]
    unchanged: list[str]

    @property
    def clean(self) -> bool:
        return not self.added and not self.modified and not self.deleted


@dataclass(frozen=True)
class WorkspaceCheckpoint:
    id: str
    label: str
    created_at: float
    root: Path
    manifest_path: Path
    files: dict[str, CheckpointFile]

    @classmethod
    def create(
        cls,
        workspace: str | Path,
        checkpoint_root: str | Path,
        *,
        label: str = "",
    ) -> "WorkspaceCheckpoint":
        workspace_path = Path(workspace).expanduser().resolve()
        checkpoint_id = uuid4().hex
        target_root = Path(checkpoint_root).expanduser().resolve() / checkpoint_id
        files_root = target_root / "files"
        files_root.mkdir(parents=True, exist_ok=True)

        files: dict[str, CheckpointFile] = {}
        for path in sorted(workspace_path.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(workspace_path).as_posix()
            target = files_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            files[rel] = CheckpointFile(size=path.stat().st_size, sha256=_sha256(path))

        manifest = {
            "id": checkpoint_id,
            "label": label,
            "created_at": time(),
            "files": {name: file.__dict__ for name, file in files.items()},
        }
        manifest_path = target_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return cls(
            id=checkpoint_id,
            label=label,
            created_at=manifest["created_at"],
            root=target_root,
            manifest_path=manifest_path,
            files=files,
        )

    @classmethod
    def load(cls, manifest_path: str | Path) -> "WorkspaceCheckpoint":
        path = Path(manifest_path).expanduser().resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        files = {
            name: CheckpointFile(size=int(value["size"]), sha256=str(value["sha256"]))
            for name, value in data.get("files", {}).items()
        }
        return cls(
            id=data["id"],
            label=data.get("label") or "",
            created_at=float(data.get("created_at") or 0),
            root=path.parent,
            manifest_path=path,
            files=files,
        )

    @classmethod
    def restore(
        cls,
        manifest_path: str | Path,
        workspace: str | Path,
        *,
        clean: bool = False,
    ) -> "WorkspaceCheckpoint":
        checkpoint = cls.load(manifest_path)
        workspace_path = Path(workspace).expanduser().resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        if clean:
            current = _scan_files(workspace_path)
            for rel in sorted(set(current) - set(checkpoint.files)):
                (workspace_path / rel).unlink()
        files_root = checkpoint.root / "files"
        for rel in checkpoint.files:
            source = files_root / rel
            target = workspace_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if clean:
            _remove_empty_dirs(workspace_path)
        return checkpoint

    @classmethod
    def diff(cls, manifest_path: str | Path, workspace: str | Path) -> WorkspaceDiff:
        checkpoint = cls.load(manifest_path)
        workspace_path = Path(workspace).expanduser().resolve()
        current = _scan_files(workspace_path)
        checkpoint_files = checkpoint.files

        added = sorted(path for path in current if path not in checkpoint_files)
        deleted = sorted(path for path in checkpoint_files if path not in current)
        modified = sorted(
            path
            for path in current.keys() & checkpoint_files.keys()
            if current[path].sha256 != checkpoint_files[path].sha256
        )
        unchanged = sorted(
            path
            for path in current.keys() & checkpoint_files.keys()
            if current[path].sha256 == checkpoint_files[path].sha256
        )
        return WorkspaceDiff(added=added, modified=modified, deleted=deleted, unchanged=unchanged)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_files(root: Path) -> dict[str, CheckpointFile]:
    if not root.exists():
        return {}
    files: dict[str, CheckpointFile] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = CheckpointFile(size=path.stat().st_size, sha256=_sha256(path))
    return files


def _remove_empty_dirs(root: Path) -> None:
    directories = (item for item in root.rglob("*") if item.is_dir())
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass
