from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from time import time
from uuid import uuid4

from harness.storage import atomic_write_text, file_lock


class RunStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunRecord:
    id: str
    prompt: str
    workspace: str
    status: str = RunStatus.IN_PROGRESS.value
    session_id: str | None = None
    turn_id: str | None = None
    task_id: str | None = None
    stop_reason: str | None = None
    iterations: int = 0
    started_at: float = field(default_factory=time)
    ended_at: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls, *, prompt: str, workspace: str, session_id: str | None = None, task_id: str | None = None) -> "RunRecord":
        return cls(id=uuid4().hex, prompt=prompt, workspace=workspace, session_id=session_id, task_id=task_id)

    @classmethod
    def pending(cls, *, prompt: str, workspace: str, task_id: str | None = None) -> "RunRecord":
        return cls(id=uuid4().hex, prompt=prompt, workspace=workspace, status=RunStatus.PENDING.value, task_id=task_id)

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        return cls(
            id=str(data["id"]),
            prompt=str(data.get("prompt") or ""),
            workspace=str(data.get("workspace") or ""),
            status=str(data.get("status") or RunStatus.IN_PROGRESS.value),
            session_id=data.get("session_id"),
            turn_id=data.get("turn_id"),
            task_id=data.get("task_id"),
            stop_reason=data.get("stop_reason"),
            iterations=int(data.get("iterations") or 0),
            started_at=float(data.get("started_at") or time()),
            ended_at=float(data["ended_at"]) if data.get("ended_at") is not None else None,
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class RunStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "runs.json"
        self.lock_path = self.root / "runs.lock"
        if not self.path.exists():
            with file_lock(self.lock_path):
                if not self.path.exists():
                    self._write_unlocked({})

    def create(self, *, prompt: str, workspace: str, session_id: str | None = None, task_id: str | None = None) -> RunRecord:
        record = RunRecord.new(prompt=prompt, workspace=workspace, session_id=session_id, task_id=task_id)
        with file_lock(self.lock_path):
            records = self._read_unlocked()
            records[record.id] = record
            self._write_unlocked(records)
        return record

    def enqueue(self, *, prompt: str, workspace: str, task_id: str | None = None) -> RunRecord:
        record = RunRecord.pending(prompt=prompt, workspace=workspace, task_id=task_id)
        with file_lock(self.lock_path):
            records = self._read_unlocked()
            records[record.id] = record
            self._write_unlocked(records)
        return record

    def load(self, run_id: str) -> RunRecord:
        with file_lock(self.lock_path):
            records = self._read_unlocked()
        try:
            return records[run_id]
        except KeyError as exc:
            raise KeyError(f"run not found: {run_id}") from exc

    def list(
        self,
        *,
        status: RunStatus | str | None = None,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[RunRecord]:
        with file_lock(self.lock_path):
            records = sorted(self._read_unlocked().values(), key=lambda record: (record.started_at, record.id))
        if status is not None:
            status_value = _status_value(status)
            records = [record for record in records if record.status == status_value]
        if session_id is not None:
            records = [record for record in records if record.session_id == session_id]
        if limit is not None:
            records = records[-limit:]
        return records

    def finish(
        self,
        run_id: str,
        *,
        status: RunStatus | str,
        session_id: str,
        turn_id: str,
        stop_reason: str,
        iterations: int,
        metadata: dict[str, str] | None = None,
    ) -> RunRecord:
        with file_lock(self.lock_path):
            records = self._read_unlocked()
            if run_id not in records:
                raise KeyError(f"run not found: {run_id}")
            record = records[run_id]
            record.status = _status_value(status)
            record.session_id = session_id
            record.turn_id = turn_id
            record.stop_reason = stop_reason
            record.iterations = iterations
            record.ended_at = time()
            if metadata:
                record.metadata.update(metadata)
            records[run_id] = record
            self._write_unlocked(records)
            return record

    def start(self, run_id: str, *, session_id: str | None = None) -> RunRecord:
        with file_lock(self.lock_path):
            records = self._read_unlocked()
            if run_id not in records:
                raise KeyError(f"run not found: {run_id}")
            record = records[run_id]
            if record.status != RunStatus.PENDING.value:
                raise ValueError(f"run {run_id} is {record.status}, expected pending")
            record.status = RunStatus.IN_PROGRESS.value
            record.started_at = time()
            if session_id is not None:
                record.session_id = session_id
            records[run_id] = record
            self._write_unlocked(records)
            return record

    def cancel(self, run_id: str, *, reason: str = "") -> RunRecord:
        with file_lock(self.lock_path):
            records = self._read_unlocked()
            if run_id not in records:
                raise KeyError(f"run not found: {run_id}")
            record = records[run_id]
            if record.status not in {RunStatus.PENDING.value, RunStatus.IN_PROGRESS.value}:
                raise ValueError(f"run {run_id} is {record.status} and cannot be cancelled")
            record.status = RunStatus.CANCELLED.value
            record.stop_reason = "cancelled"
            record.ended_at = time()
            if reason:
                record.metadata["cancel_reason"] = reason
            records[run_id] = record
            self._write_unlocked(records)
            return record

    def _read_unlocked(self) -> dict[str, RunRecord]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return {run_id: RunRecord.from_dict(item) for run_id, item in data.items()}

    def _write_unlocked(self, records: dict[str, RunRecord]) -> None:
        data = {run_id: record.to_dict() for run_id, record in records.items()}
        atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _status_value(status: RunStatus | str) -> str:
    value = status.value if isinstance(status, RunStatus) else str(status)
    allowed = {item.value for item in RunStatus}
    if value not in allowed:
        raise ValueError(f"invalid run status {value!r}; expected one of {', '.join(sorted(allowed))}")
    return value
