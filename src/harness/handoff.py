from __future__ import annotations

from dataclasses import dataclass

from harness.session import Session
from harness.tasks import Task


@dataclass(frozen=True)
class HandoffBuilder:
    recent_messages: int = 8

    def render(self, *, session: Session, task: Task | None = None, trace_summary: dict | None = None) -> str:
        lines = [
            "# Harness Handoff",
            "",
            "## Session",
            f"- id: {session.id}",
            f"- workspace: {session.workspace}",
            f"- messages: {len(session.messages)}",
            f"- total_tokens: {session.usage.get('total_tokens', 0)}",
            f"- cost_usd: {session.cost_usd:.6f}",
        ]
        if task:
            lines.extend(
                [
                    "",
                    "## Task",
                    f"- id: {task.id}",
                    f"- title: {task.title}",
                    f"- status: {task.status}",
                ]
            )
            if task.description:
                lines.append(f"- description: {task.description}")
        if trace_summary:
            lines.extend(["", "## Trace Summary"])
            for key in sorted(trace_summary):
                lines.append(f"- {key}: {trace_summary[key]}")
        lines.extend(["", "## Recent Messages"])
        recent = session.messages[-self.recent_messages :]
        for message in recent:
            label = message.role if not message.name else f"{message.role}:{message.name}"
            content = _single_line(message.content)
            lines.append(f"- {label}: {content}")
        return "\n".join(lines).rstrip() + "\n"


def _single_line(text: str, *, limit: int = 500) -> str:
    value = " ".join(text.strip().split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
