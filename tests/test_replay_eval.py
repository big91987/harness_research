from pathlib import Path
import json
import os
import subprocess
import sys

from harness.eval import EvalExpectation, EvalSuiteStore, evaluate_trace
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


def test_eval_suite_can_add_case_from_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(trace_path)
    trace.record("tool_call", session_id="s1", name="write_file", is_error=False)
    trace.record("tool_call", session_id="s1", name="grep", is_error=False)
    trace.record("model_response", session_id="s1", usage={"total_tokens": 42}, cost_usd=0.01)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="created file")
    suite = EvalSuiteStore(tmp_path / "golden.json")

    case = suite.add_case_from_trace("derived", trace=trace_path)

    assert case["expect"] == {
        "final_text_contains": "created file",
        "max_cost_usd": 0.011,
        "max_tool_errors": 0,
        "max_total_tokens": 42,
        "required_tools": ["grep", "write_file"],
        "stop_reason": "final_answer",
    }
    assert suite.run().passed


def test_eval_suite_store_serializes_concurrent_adds(tmp_path: Path) -> None:
    suite = tmp_path / "golden.json"
    script = """
from harness.eval import EvalSuiteStore
import sys

EvalSuiteStore(sys.argv[1]).add_case(sys.argv[2], trace=sys.argv[3], expect={"stop_reason": "final_answer"})
"""

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(suite), f"case-{index}", f"trace-{index}.jsonl"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        for index in range(8)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stdout + stderr

    cases = EvalSuiteStore(suite).list_cases()

    assert {case["name"] for case in cases} == {f"case-{index}" for index in range(8)}


def test_cli_eval_suite_add_from_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(trace_path)
    trace.record("tool_call", session_id="s1", name="read_file", is_error=False)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="ok")
    suite = tmp_path / "golden.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "eval-suite",
            str(suite),
            "--add-from-trace",
            "read-smoke",
            "--trace-path",
            str(trace_path),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    data = json.loads(suite.read_text(encoding="utf-8"))
    assert "added: read-smoke" in result.stdout
    assert data["cases"][0]["expect"]["required_tools"] == ["read_file"]
