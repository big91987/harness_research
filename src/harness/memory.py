from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness.storage import atomic_write_text, file_lock, locked_append_text


@dataclass
class MarkdownMemoryStore:
    root: Path

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "memory.md"
        self.lock_path = self.root / "memory.lock"
        if not self.path.exists():
            with file_lock(self.lock_path):
                if not self.path.exists():
                    atomic_write_text(self.path, "# Harness Memory\n\n")

    def add(self, text: str) -> None:
        locked_append_text(self.path, f"- {text.strip()}\n")

    def list(self) -> list[str]:
        return [line.strip() for line in self._read_lines() if line.strip().startswith("- ")]

    def clear(self) -> None:
        with file_lock(self.lock_path):
            atomic_write_text(self.path, "# Harness Memory\n\n")

    def search(self, query: str) -> list[str]:
        q = query.lower()
        return [line.strip() for line in self._read_lines() if q in line.lower()]

    def render_context(self, limit: int = 20) -> str:
        lines = [line.strip() for line in self._read_lines() if line.strip().startswith("- ")]
        if not lines:
            return ""
        return "Relevant persistent memory:\n" + "\n".join(lines[-limit:])

    def _read_lines(self) -> list[str]:
        with file_lock(self.lock_path):
            return self.path.read_text(encoding="utf-8").splitlines()
