from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from uuid import uuid4


@dataclass(frozen=True)
class Artifact:
    id: str
    path: str
    relative_path: str
    kind: str
    size: int
    sha256: str
    created_at: float


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "artifacts.jsonl"

    def register_file(
        self,
        path: str | Path,
        *,
        workspace_root: str | Path | None = None,
        kind: str = "file",
    ) -> Artifact:
        file_path = Path(path).expanduser().resolve()
        rel = file_path.name
        if workspace_root:
            rel = file_path.relative_to(Path(workspace_root).expanduser().resolve()).as_posix()
        artifact = Artifact(
            id=uuid4().hex,
            path=str(file_path),
            relative_path=rel,
            kind=kind,
            size=file_path.stat().st_size,
            sha256=_sha256(file_path),
            created_at=time(),
        )
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(artifact), ensure_ascii=False, sort_keys=True) + "\n")
        return artifact

    def list(self) -> list[Artifact]:
        if not self.index_path.exists():
            return []
        artifacts: list[Artifact] = []
        with self.index_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    artifacts.append(Artifact(**json.loads(line)))
        return artifacts

    def get(self, artifact_id: str) -> Artifact | None:
        return next((artifact for artifact in self.list() if artifact.id == artifact_id), None)

    def verify(self, artifact_id: str) -> bool:
        artifact = self.get(artifact_id)
        if artifact is None:
            return False
        path = Path(artifact.path)
        return path.exists() and path.stat().st_size == artifact.size and _sha256(path) == artifact.sha256


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

