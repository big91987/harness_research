from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any

from harness.cost import canonical_usage


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
        return summarize_events(self.read_events())


class TraceQuery:
    def __init__(self, recorder: TraceRecorder) -> None:
        self.recorder = recorder

    def events(
        self,
        *,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        events = self.recorder.read_events()
        if session_id is not None:
            events = [event for event in events if event.get("session_id") == session_id]
        if event_type is not None:
            events = [event for event in events if event.get("type") == event_type]
        if limit is not None:
            events = events[-limit:]
        return events

    def summary(self, *, session_id: str | None = None, event_type: str | None = None) -> dict[str, int]:
        return summarize_events(self.events(session_id=session_id, event_type=event_type))


def summarize_events(events: list[dict[str, Any]]) -> dict[str, int]:
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
        "total_tokens": sum(
            canonical_usage(dict(event.get("usage") or {}))["total_tokens"]
            for event in events
            if event.get("type") == "model_response"
        ),
        "cost_usd_micros": int(
            round(
                sum(
                    float(event.get("cost_usd") or 0.0)
                    for event in events
                    if event.get("type") == "model_response"
                )
                * 1_000_000
            )
        ),
    }
