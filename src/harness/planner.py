from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import time
from uuid import uuid4

from harness.storage import atomic_write_text, file_lock


@dataclass
class PlanStep:
    index: int
    title: str
    status: str = "pending"


@dataclass
class Plan:
    id: str
    title: str
    steps: list[PlanStep]
    status: str = "pending"
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        return cls(
            id=data["id"],
            title=data["title"],
            steps=[PlanStep(**item) for item in data.get("steps", [])],
            status=data.get("status") or "pending",
            created_at=float(data.get("created_at") or time()),
            updated_at=float(data.get("updated_at") or time()),
        )


class TaskPlanner:
    def plan(self, prompt: str) -> Plan:
        parts = [part.strip(" .") for part in re.split(r",|\n|;|(?:\s+then\s+)", prompt, flags=re.I) if part.strip(" .")]
        if not parts:
            parts = [prompt.strip() or "Complete task"]
        steps = [PlanStep(index=index, title=part) for index, part in enumerate(parts, start=1)]
        return Plan(id=uuid4().hex, title=prompt.strip() or "Untitled plan", steps=steps)


class PlanStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.root / "plans.lock"

    def save(self, plan: Plan) -> Plan:
        plan.updated_at = time()
        with file_lock(self.lock_path):
            atomic_write_text(self._path(plan.id), json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return plan

    def load(self, plan_id: str) -> Plan | None:
        path = self._path(plan_id)
        if not path.exists():
            return None
        with file_lock(self.lock_path):
            return Plan.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[Plan]:
        with file_lock(self.lock_path):
            return [Plan.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(self.root.glob("*.json"))]

    def update_step(self, plan_id: str, step_index: int, *, status: str) -> Plan:
        plan = self.load(plan_id)
        if plan is None:
            raise ValueError(f"plan not found: {plan_id}")
        for step in plan.steps:
            if step.index == step_index:
                step.status = status
                break
        else:
            raise ValueError(f"step not found: {step_index}")
        if all(step.status == "completed" for step in plan.steps):
            plan.status = "completed"
        elif any(step.status == "in_progress" for step in plan.steps):
            plan.status = "in_progress"
        else:
            plan.status = "pending"
        return self.save(plan)

    def _path(self, plan_id: str) -> Path:
        return self.root / f"{plan_id}.json"
