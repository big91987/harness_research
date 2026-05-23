from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path


class SkillStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, name: str, body: str, *, description: str = "") -> Path:
        skill_name = _normalize_name(name)
        path = self.root / f"{skill_name}.md"
        text = f"---\ndescription: {description.strip()}\n---\n\n{body.strip()}\n"
        path.write_text(text, encoding="utf-8")
        return path

    def list(self) -> list[Skill]:
        return [self._read(path) for path in sorted(self.root.glob("*.md"))]

    def get(self, name: str) -> Skill | None:
        path = self.root / f"{_normalize_name(name)}.md"
        if not path.exists():
            return None
        return self._read(path)

    def delete(self, name: str) -> bool:
        path = self.root / f"{_normalize_name(name)}.md"
        if not path.exists():
            return False
        path.unlink()
        return True

    def search(self, query: str, *, limit: int = 5) -> list[Skill]:
        terms = [term for term in re.split(r"\W+", query.lower()) if term]
        if not terms:
            return self.list()[:limit]
        scored: list[tuple[int, Skill]] = []
        for skill in self.list():
            haystack = f"{skill.name}\n{skill.description}\n{skill.body}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [skill for _, skill in scored[:limit]]

    def render_context(self, query: str, *, limit: int = 3) -> str:
        skills = self.search(query, limit=limit)
        if not skills:
            return ""
        blocks = ["Available skills:"]
        for skill in skills:
            header = f"- {skill.name}"
            if skill.description:
                header += f": {skill.description}"
            blocks.append(header)
            blocks.append(_indent(skill.body))
        return "\n".join(blocks)

    def _read(self, path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        description = ""
        body = text
        if text.startswith("---\n"):
            _, frontmatter, body = text.split("---\n", 2)
            for line in frontmatter.splitlines():
                key, sep, value = line.partition(":")
                if sep and key.strip() == "description":
                    description = value.strip()
        return Skill(
            name=path.stem,
            description=description,
            body=body.strip(),
            path=path,
        )


def _normalize_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(name).name.strip().lower())
    normalized = normalized.strip("-_")
    if not normalized:
        raise ValueError("skill name must contain at least one letter or number")
    return normalized


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" if line else "" for line in text.strip().splitlines())
