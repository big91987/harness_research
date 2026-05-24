from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from uuid import uuid4

from harness.schema import Message
from harness.storage import atomic_write_text


@dataclass
class Session:
    id: str
    workspace: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    metadata: dict[str, str] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })
    cost_usd: float = 0.0

    @classmethod
    def new(cls, workspace: str) -> "Session":
        return cls(id=uuid4().hex, workspace=workspace)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["messages"] = [message.to_dict() for message in self.messages]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data["id"],
            workspace=data["workspace"],
            messages=[Message.from_dict(item) for item in data.get("messages", [])],
            created_at=float(data.get("created_at") or time()),
            updated_at=float(data.get("updated_at") or time()),
            metadata=dict(data.get("metadata") or {}),
            usage={
                "prompt_tokens": int((data.get("usage") or {}).get("prompt_tokens", 0)),
                "completion_tokens": int((data.get("usage") or {}).get("completion_tokens", 0)),
                "total_tokens": int((data.get("usage") or {}).get("total_tokens", 0)),
            },
            cost_usd=float(data.get("cost_usd") or 0.0),
        )


class JsonlSessionStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.jsonl"

    def save(self, session: Session) -> None:
        session.updated_at = time()
        path = self.path_for(session.id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(session.to_dict(), ensure_ascii=False) + "\n")

    def load(self, session_id: str) -> Session | None:
        path = self.path_for(session_id)
        if not path.exists():
            return None
        last = ""
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last = line
        if not last:
            return None
        return Session.from_dict(json.loads(last))

    def history(self, session_id: str) -> list[Session]:
        path = self.path_for(session_id)
        if not path.exists():
            return []
        snapshots: list[Session] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    snapshots.append(Session.from_dict(json.loads(line)))
        return snapshots

    def list(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.jsonl"))

    def summaries(
        self,
        *,
        workspace_contains: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        summaries: list[dict] = []
        for session_id in self.list():
            session = self.load(session_id)
            if session is None:
                continue
            if workspace_contains and workspace_contains not in session.workspace:
                continue
            last = session.messages[-1] if session.messages else None
            summaries.append(
                {
                    "id": session.id,
                    "workspace": session.workspace,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "messages": len(session.messages),
                    "usage_prompt_tokens": int(session.usage.get("prompt_tokens", 0)),
                    "usage_completion_tokens": int(session.usage.get("completion_tokens", 0)),
                    "usage_total_tokens": int(session.usage.get("total_tokens", 0)),
                    "cost_usd": session.cost_usd,
                    "last_role": last.role if last else None,
                    "last_content": last.content if last else "",
                    "metadata": dict(session.metadata),
                }
            )
        summaries.sort(key=lambda item: (item["updated_at"], item["id"]))
        if limit is not None:
            summaries = summaries[-limit:]
        return summaries


class SessionBundle:
    version = 1

    @classmethod
    def export(cls, session: Session | None, path: str | Path) -> Path:
        if session is None:
            raise ValueError("session is required")
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            target,
            json.dumps(
                {
                    "version": cls.version,
                    "session": session.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return target

    @classmethod
    def import_into(cls, path: str | Path, store: JsonlSessionStore) -> Session:
        bundle_path = Path(path).expanduser().resolve()
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
        if int(data.get("version") or 0) != cls.version:
            raise ValueError(f"unsupported session bundle version: {data.get('version')}")
        session = Session.from_dict(data["session"])
        store.save(session)
        return session
