from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from time import time
from uuid import uuid4

from harness.storage import atomic_write_text, file_lock


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    status: str = TaskStatus.TODO.value
    session_id: str | None = None
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    metadata: dict[str, str] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            description=str(data.get("description") or ""),
            status=str(data.get("status") or TaskStatus.TODO.value),
            session_id=data.get("session_id"),
            created_at=float(data.get("created_at") or time()),
            updated_at=float(data.get("updated_at") or time()),
            metadata=dict(data.get("metadata") or {}),
            history=list(data.get("history") or []),
        )


class TaskStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.json"
        self.lock_path = self.root / "tasks.lock"
        if not self.path.exists():
            with file_lock(self.lock_path):
                if not self.path.exists():
                    self._write_unlocked({})

    def create(self, title: str, *, description: str = "", metadata: dict[str, str] | None = None) -> Task:
        task = Task(
            id=uuid4().hex,
            title=title.strip(),
            description=description.strip(),
            metadata=metadata or {},
        )
        if not task.title:
            raise ValueError("task title is required")
        task.history.append(
            {
                "ts": task.created_at,
                "type": "created",
                "changes": {
                    "title": task.title,
                    "description": task.description,
                    "metadata": dict(task.metadata),
                },
            }
        )
        with file_lock(self.lock_path):
            tasks = self._read_unlocked()
            tasks[task.id] = task
            self._write_unlocked(tasks)
        return task

    def load(self, task_id: str) -> Task:
        with file_lock(self.lock_path):
            tasks = self._read_unlocked()
        try:
            return tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task not found: {task_id}") from exc

    def list(self, *, status: TaskStatus | str | None = None, session_id: str | None = None) -> list[Task]:
        with file_lock(self.lock_path):
            tasks = sorted(self._read_unlocked().values(), key=lambda task: (task.created_at, task.id))
        if status is not None:
            status_value = _status_value(status)
            tasks = [task for task in tasks if task.status == status_value]
        if session_id is not None:
            tasks = [task for task in tasks if task.session_id == session_id]
        return tasks

    def delete(self, task_id: str) -> bool:
        with file_lock(self.lock_path):
            tasks = self._read_unlocked()
            if task_id not in tasks:
                return False
            del tasks[task_id]
            self._write_unlocked(tasks)
        return True

    def history(self, task_id: str) -> list[dict]:
        return list(self.load(task_id).history)

    def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TaskStatus | str | None = None,
        session_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Task:
        with file_lock(self.lock_path):
            tasks = self._read_unlocked()
            if task_id not in tasks:
                raise KeyError(f"task not found: {task_id}")
            task = tasks[task_id]
            changes: dict[str, object] = {}
            if title is not None:
                task.title = title.strip()
                changes["title"] = task.title
            if description is not None:
                task.description = description.strip()
                changes["description"] = task.description
            if status is not None:
                task.status = _status_value(status)
                changes["status"] = task.status
            if session_id is not None:
                task.session_id = session_id
                changes["session_id"] = session_id
            if metadata is not None:
                task.metadata.update(metadata)
                changes["metadata"] = dict(metadata)
            task.updated_at = time()
            if changes:
                task.history.append({"ts": task.updated_at, "type": "updated", "changes": changes})
            tasks[task_id] = task
            self._write_unlocked(tasks)
            return task

    def render_context(self, task_id: str) -> str:
        task = self.load(task_id)
        lines = [
            "Active task:",
            f"- id: {task.id}",
            f"- title: {task.title}",
            f"- status: {task.status}",
        ]
        if task.description:
            lines.append(f"- description: {task.description}")
        if task.session_id:
            lines.append(f"- session: {task.session_id}")
        return "\n".join(lines)

    def _read_unlocked(self) -> dict[str, Task]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {task_id: Task.from_dict(item) for task_id, item in data.items()}

    def _write_unlocked(self, tasks: dict[str, Task]) -> None:
        data = {task_id: task.to_dict() for task_id, task in tasks.items()}
        atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _status_value(status: TaskStatus | str) -> str:
    value = status.value if isinstance(status, TaskStatus) else str(status)
    allowed = {item.value for item in TaskStatus}
    if value not in allowed:
        raise ValueError(f"invalid task status {value!r}; expected one of {', '.join(sorted(allowed))}")
    return value
