from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any


class AuditLog:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve() if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event_type: str, **data: Any) -> None:
        if self.path is None:
            return
        event = {"ts": time(), "type": event_type, **data}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def read_events(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    events.append(json.loads(line))
        return events

