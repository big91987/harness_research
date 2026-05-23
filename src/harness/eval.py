from __future__ import annotations

from dataclasses import dataclass, field
import json
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


@dataclass
class GoldenCaseReport:
    name: str
    report: EvalReport


@dataclass
class GoldenSuiteReport:
    passed: bool
    total: int
    passed_count: int
    cases: list[GoldenCaseReport]


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


def run_golden_suite(path: str | Path) -> GoldenSuiteReport:
    suite_path = Path(path).expanduser().resolve()
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    case_reports: list[GoldenCaseReport] = []
    for index, case in enumerate(data.get("cases", []), start=1):
        expect = case.get("expect") or {}
        trace = case["trace"]
        if not Path(trace).is_absolute():
            trace = str((suite_path.parent / trace).resolve())
        report = evaluate_trace(
            trace,
            EvalExpectation(
                stop_reason=expect.get("stop_reason"),
                max_tool_errors=expect.get("max_tool_errors"),
                required_tools=list(expect.get("required_tools") or []),
                final_text_contains=expect.get("final_text_contains"),
            ),
        )
        case_reports.append(GoldenCaseReport(name=case.get("name") or f"case-{index}", report=report))
    passed_count = sum(1 for case in case_reports if case.report.passed)
    return GoldenSuiteReport(
        passed=passed_count == len(case_reports) and bool(case_reports),
        total=len(case_reports),
        passed_count=passed_count,
        cases=case_reports,
    )
