from __future__ import annotations

from collections.abc import Callable
from time import time
from typing import Any


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._history: list[dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event_type: str, **data: Any) -> dict[str, Any]:
        event = {"ts": time(), "type": event_type, **data}
        self._history.append(event)
        for handler in [*self._subscribers.get(event_type, []), *self._subscribers.get("*", [])]:
            handler(dict(event))
        return event

    def history(self, *, event_type: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        events = [dict(event) for event in self._history]
        if event_type is not None:
            events = [event for event in events if event.get("type") == event_type]
        if limit is not None:
            events = events[-limit:]
        return events
