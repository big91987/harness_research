from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class MarkdownMemoryStore:
    root: Path

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "memory.md"
        if not self.path.exists():
            self.path.write_text("# Harness Memory\n\n", encoding="utf-8")

    def add(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"- {text.strip()}\n")

    def list(self) -> list[str]:
        return [
            line.strip()
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")
        ]

    def clear(self) -> None:
        self.path.write_text("# Harness Memory\n\n", encoding="utf-8")

    def search(self, query: str) -> list[str]:
        q = query.lower()
        return [line.strip() for line in self.path.read_text(encoding="utf-8").splitlines() if q in line.lower()]

    def render_context(self, limit: int = 20) -> str:
        lines = [
            line.strip()
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")
        ]
        if not lines:
            return ""
        return "Relevant persistent memory:\n" + "\n".join(lines[-limit:])
