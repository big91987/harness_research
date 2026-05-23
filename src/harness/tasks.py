from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from time import time
from uuid import uuid4


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
        )


class TaskStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.json"
        if not self.path.exists():
            self._write({})

    def create(self, title: str, *, description: str = "", metadata: dict[str, str] | None = None) -> Task:
        task = Task(
            id=uuid4().hex,
            title=title.strip(),
            description=description.strip(),
            metadata=metadata or {},
        )
        if not task.title:
            raise ValueError("task title is required")
        tasks = self._read()
        tasks[task.id] = task
        self._write(tasks)
        return task

    def load(self, task_id: str) -> Task:
        tasks = self._read()
        try:
            return tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task not found: {task_id}") from exc

    def list(self, *, status: TaskStatus | str | None = None) -> list[Task]:
        tasks = sorted(self._read().values(), key=lambda task: (task.created_at, task.id))
        if status is None:
            return tasks
        status_value = _status_value(status)
        return [task for task in tasks if task.status == status_value]

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
        tasks = self._read()
        if task_id not in tasks:
            raise KeyError(f"task not found: {task_id}")
        task = tasks[task_id]
        if title is not None:
            task.title = title.strip()
        if description is not None:
            task.description = description.strip()
        if status is not None:
            task.status = _status_value(status)
        if session_id is not None:
            task.session_id = session_id
        if metadata is not None:
            task.metadata.update(metadata)
        task.updated_at = time()
        tasks[task_id] = task
        self._write(tasks)
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

    def _read(self) -> dict[str, Task]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {task_id: Task.from_dict(item) for task_id, item in data.items()}

    def _write(self, tasks: dict[str, Task]) -> None:
        data = {task_id: task.to_dict() for task_id, task in tasks.items()}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _status_value(status: TaskStatus | str) -> str:
    value = status.value if isinstance(status, TaskStatus) else str(status)
    allowed = {item.value for item in TaskStatus}
    if value not in allowed:
        raise ValueError(f"invalid task status {value!r}; expected one of {', '.join(sorted(allowed))}")
    return value
