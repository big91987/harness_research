from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from harness.model import ModelClient
from harness.schema import Message
from harness.session import Session
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


SESSION_MEMORY_SYSTEM_PROMPT = """You extract durable memory for a local agent harness.
Return only JSON: an array of short strings.
Keep only stable facts, user preferences, project constraints, and recurring workflow guidance.
Do not include transient task status, greetings, speculation, or secrets."""


@dataclass
class SessionMemoryExtractor:
    model: ModelClient
    memory: MarkdownMemoryStore
    max_messages: int = 80
    max_items: int = 20

    def extract(self, session: Session) -> list[str]:
        transcript = self._render_transcript(session)
        response = self.model.generate(
            [
                Message.system(SESSION_MEMORY_SYSTEM_PROMPT),
                Message.user(
                    "Extract durable memory from this session transcript.\n\n"
                    f"Session: {session.id}\n"
                    f"Workspace: {session.workspace}\n\n"
                    f"{transcript}"
                ),
            ],
            [],
        )
        candidates = self._parse_items(response.content)
        existing = {self._normalize(item) for item in self.memory.list()}
        added: list[str] = []
        seen = set(existing)
        for candidate in candidates:
            item = self._clean_item(candidate)
            if not item:
                continue
            normalized = self._normalize(item)
            if normalized in seen:
                continue
            self.memory.add(item)
            added.append(item)
            seen.add(normalized)
            if len(added) >= self.max_items:
                break
        return added

    def _render_transcript(self, session: Session) -> str:
        messages = session.messages[-self.max_messages :]
        lines: list[str] = []
        for message in messages:
            label = message.role
            if message.name:
                label = f"{label}:{message.name}"
            content = message.content.strip()
            if not content:
                continue
            lines.append(f"{label}: {content}")
        return "\n".join(lines)

    def _parse_items(self, text: str) -> list[str]:
        payload = self._loads_json(text)
        if isinstance(payload, list):
            return [self._item_to_text(item) for item in payload]
        if isinstance(payload, dict):
            for key in ("memories", "items", "facts"):
                if isinstance(payload.get(key), list):
                    return [self._item_to_text(item) for item in payload[key]]
        raise ValueError("memory extraction response must be a JSON array or an object with memories/items/facts")

    def _loads_json(self, text: str):  # noqa: ANN001 - JSON can be any supported shape.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            start = min((idx for idx in (cleaned.find("["), cleaned.find("{")) if idx >= 0), default=-1)
            end = max(cleaned.rfind("]"), cleaned.rfind("}"))
            if start >= 0 and end > start:
                return json.loads(cleaned[start : end + 1])
            raise ValueError(f"memory extraction response is not valid JSON: {exc.msg}") from exc

    def _item_to_text(self, item) -> str:  # noqa: ANN001 - model output is untyped JSON.
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for key in ("memory", "text", "fact", "content"):
                if item.get(key):
                    return str(item[key])
        return ""

    def _clean_item(self, item: str) -> str:
        cleaned = " ".join(item.strip().split())
        if cleaned.startswith("- "):
            cleaned = cleaned[2:].strip()
        return cleaned

    def _normalize(self, item: str) -> str:
        return self._clean_item(item).rstrip(".").casefold()
