from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any


class TraceRecorder:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, **data: Any) -> None:
        if not self.path:
            return
        event = {"ts": time(), "type": event_type, **data}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path or not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    events.append(json.loads(line))
        return events

    def summary(self) -> dict[str, int]:
        events = self.read_events()
        return {
            "events": len(events),
            "turns": sum(1 for event in events if event.get("type") == "turn_end"),
            "model_calls": sum(1 for event in events if event.get("type") == "model_call"),
            "tool_calls": sum(1 for event in events if event.get("type") == "tool_call"),
            "tool_errors": sum(
                1
                for event in events
                if event.get("type") == "tool_call" and bool(event.get("is_error"))
            ),
        }
