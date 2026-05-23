from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Hook:
    event: str
    command: list[str]
    timeout_seconds: int = 10


@dataclass(frozen=True)
class HookResult:
    event: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class HookRunnerProtocol(Protocol):
    def run(self, event_type: str, payload: dict[str, Any]) -> list[HookResult]:
        ...


class HookRunner:
    def __init__(self, hooks: list[Hook] | None = None, *, cwd: str | Path | None = None) -> None:
        self.hooks = hooks or []
        self.cwd = Path(cwd).expanduser().resolve() if cwd else None

    @classmethod
    def from_config(cls, path: str | Path | None, *, cwd: str | Path | None = None) -> "HookRunner":
        if not path:
            return cls(cwd=cwd)
        config_path = Path(path).expanduser()
        if not config_path.exists():
            return cls(cwd=cwd)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        hooks = [
            Hook(
                event=str(item["event"]),
                command=[str(part) for part in item["command"]],
                timeout_seconds=int(item.get("timeout_seconds") or 10),
            )
            for item in data.get("hooks", [])
            if item.get("event") and item.get("command")
        ]
        return cls(hooks, cwd=cwd)

    def run(self, event_type: str, payload: dict[str, Any]) -> list[HookResult]:
        results: list[HookResult] = []
        stdin = json.dumps({"event": event_type, **payload}, ensure_ascii=False)
        for hook in self.hooks:
            if hook.event != event_type:
                continue
            try:
                completed = subprocess.run(
                    hook.command,
                    input=stdin,
                    text=True,
                    capture_output=True,
                    cwd=self.cwd,
                    timeout=hook.timeout_seconds,
                    check=False,
                )
                results.append(
                    HookResult(
                        event=event_type,
                        command=hook.command,
                        returncode=completed.returncode,
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                    )
                )
            except subprocess.TimeoutExpired as exc:
                results.append(
                    HookResult(
                        event=event_type,
                        command=hook.command,
                        returncode=124,
                        stdout=exc.stdout or "",
                        stderr=f"hook timed out after {hook.timeout_seconds}s",
                    )
                )
            except OSError as exc:
                results.append(
                    HookResult(
                        event=event_type,
                        command=hook.command,
                        returncode=127,
                        stdout="",
                        stderr=str(exc),
                    )
                )
        return results
