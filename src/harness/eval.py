from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from harness.trace import TraceRecorder


@dataclass
class EvalExpectation:
    stop_reason: str | None = None
    max_tool_errors: int | None = None
    required_tools: list[str] = field(default_factory=list)
    final_text_contains: str | None = None


@dataclass
class EvalReport:
    passed: bool
    checks: dict[str, str]


def evaluate_trace(path: str | Path, expectation: EvalExpectation) -> EvalReport:
    events = TraceRecorder(path).read_events()
    checks: dict[str, str] = {}
    turn_ends = [event for event in events if event.get("type") == "turn_end"]
    last_turn = turn_ends[-1] if turn_ends else {}

    if expectation.stop_reason is not None:
        actual = last_turn.get("stop_reason")
        checks["stop_reason"] = (
            "passed" if actual == expectation.stop_reason else f"failed: expected {expectation.stop_reason}, got {actual}"
        )

    if expectation.max_tool_errors is not None:
        errors = [
            event
            for event in events
            if event.get("type") == "tool_call" and bool(event.get("is_error"))
        ]
        checks["tool_errors"] = (
            "passed"
            if len(errors) <= expectation.max_tool_errors
            else f"failed: expected <= {expectation.max_tool_errors}, got {len(errors)}"
        )

    if expectation.required_tools:
        called = {event.get("name") for event in events if event.get("type") == "tool_call"}
        missing = [name for name in expectation.required_tools if name not in called]
        checks["required_tools"] = "passed" if not missing else f"failed: missing {', '.join(missing)}"

    if expectation.final_text_contains:
        final_text = str(last_turn.get("final_text") or "")
        checks["final_text_contains"] = (
            "passed"
            if expectation.final_text_contains in final_text
            else f"failed: final text did not contain {expectation.final_text_contains!r}"
        )

    return EvalReport(
        passed=bool(checks) and all(value == "passed" for value in checks.values()),
        checks=checks,
    )

