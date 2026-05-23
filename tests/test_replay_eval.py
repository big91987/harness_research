from pathlib import Path

from harness.eval import EvalExpectation, evaluate_trace
from harness.trace import TraceRecorder


def test_evaluate_trace_checks_stop_reason_and_tool_errors(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(trace_path)
    trace.record("tool_call", session_id="s1", name="write_file", is_error=False)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="done")

    report = evaluate_trace(
        trace_path,
        EvalExpectation(stop_reason="final_answer", max_tool_errors=0, required_tools=["write_file"]),
    )

    assert report.passed
    assert report.checks["stop_reason"] == "passed"
    assert report.checks["required_tools"] == "passed"


def test_evaluate_trace_fails_missing_required_tool(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    TraceRecorder(trace_path).record("turn_end", session_id="s1", stop_reason="final_answer")

    report = evaluate_trace(trace_path, EvalExpectation(required_tools=["grep"]))

    assert not report.passed
    assert report.checks["required_tools"].startswith("failed")


def test_evaluate_trace_checks_token_and_cost_budgets(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(trace_path)
    trace.record(
        "model_response",
        session_id="s1",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        cost_usd=0.004,
    )
    trace.record("turn_end", session_id="s1", stop_reason="final_answer")

    report = evaluate_trace(trace_path, EvalExpectation(max_total_tokens=20, max_cost_usd=0.01))

    assert report.passed
    assert report.checks["max_total_tokens"] == "passed"
    assert report.checks["max_cost_usd"] == "passed"


def test_evaluate_trace_fails_cost_budget(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(trace_path)
    trace.record("model_response", session_id="s1", usage={"total_tokens": 12}, cost_usd=0.03)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer")

    report = evaluate_trace(trace_path, EvalExpectation(max_total_tokens=20, max_cost_usd=0.01))

    assert not report.passed
    assert report.checks["max_cost_usd"].startswith("failed")
