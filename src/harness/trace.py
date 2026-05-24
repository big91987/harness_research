from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any

from harness.cost import canonical_usage
from harness.storage import file_lock, locked_append_text


class TraceRecorder:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, **data: Any) -> None:
        if not self.path:
            return
        event = {"ts": time(), "type": event_type, **data}
        locked_append_text(self.path, json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        if not self.path or not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with file_lock(self.path.with_name(f"{self.path.name}.lock")):
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
        turn_id: str | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        events = self.recorder.read_events()
        if session_id is not None:
            events = [event for event in events if event.get("session_id") == session_id]
        if turn_id is not None:
            events = [event for event in events if event.get("turn_id") == turn_id]
        if event_type is not None:
            events = [event for event in events if event.get("type") == event_type]
        if limit is not None:
            events = events[-limit:]
        return events

    def summary(
        self,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, int]:
        return summarize_events(self.events(session_id=session_id, turn_id=turn_id, event_type=event_type))

    def sessions(self, *, failures_only: bool = False) -> list[dict[str, Any]]:
        summaries = summarize_sessions(self.recorder.read_events())
        if failures_only:
            summaries = [
                summary
                for summary in summaries
                if summary.get("stop_reason") not in {None, "final_answer"} or summary.get("tool_errors", 0) > 0
            ]
        return summaries


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
        "checkpoints": sum(1 for event in events if event.get("type") == "checkpoint_created"),
        "checkpoint_restores": sum(1 for event in events if event.get("type") == "checkpoint_restored"),
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


def summarize_sessions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for event in events:
        session_id = event.get("session_id")
        if not session_id:
            continue
        summary = grouped.setdefault(
            str(session_id),
            {
                "session_id": str(session_id),
                "first_ts": event.get("ts"),
                "last_ts": event.get("ts"),
                "duration_seconds": 0.0,
                "events": 0,
                "turns": 0,
                "model_calls": 0,
                "tool_calls": 0,
                "tool_errors": 0,
                "checkpoints": 0,
                "checkpoint_restores": 0,
                "total_tokens": 0,
                "cost_usd": 0.0,
                "stop_reason": None,
                "final_text": "",
            },
        )
        summary["events"] += 1
        ts = event.get("ts")
        if isinstance(ts, (int, float)):
            if summary["first_ts"] is None or ts < summary["first_ts"]:
                summary["first_ts"] = ts
            if summary["last_ts"] is None or ts > summary["last_ts"]:
                summary["last_ts"] = ts
        event_type = event.get("type")
        if event_type == "turn_end":
            summary["turns"] += 1
            summary["stop_reason"] = event.get("stop_reason")
            summary["final_text"] = str(event.get("final_text") or "")
        elif event_type == "model_call":
            summary["model_calls"] += 1
        elif event_type == "model_response":
            summary["total_tokens"] += canonical_usage(dict(event.get("usage") or {}))["total_tokens"]
            summary["cost_usd"] += float(event.get("cost_usd") or 0.0)
        elif event_type == "tool_call":
            summary["tool_calls"] += 1
            if bool(event.get("is_error")):
                summary["tool_errors"] += 1
        elif event_type == "checkpoint_created":
            summary["checkpoints"] += 1
        elif event_type == "checkpoint_restored":
            summary["checkpoint_restores"] += 1
    for summary in grouped.values():
        first_ts = summary.get("first_ts")
        last_ts = summary.get("last_ts")
        if isinstance(first_ts, (int, float)) and isinstance(last_ts, (int, float)):
            summary["duration_seconds"] = max(0.0, last_ts - first_ts)
        summary["cost_usd"] = round(float(summary["cost_usd"]), 12)
    return sorted(grouped.values(), key=lambda summary: (summary.get("first_ts") or 0, summary["session_id"]))
