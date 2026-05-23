from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Workspace:
    root: Path

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).expanduser().resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError(f"path '{relative_path}' is outside workspace '{self.root}'")
        return candidate

