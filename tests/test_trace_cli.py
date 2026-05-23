import os
import subprocess
import sys
from pathlib import Path

from harness.trace import TraceQuery, TraceRecorder


def test_trace_recorder_summarizes_events(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(path)
    trace.record("turn_start", session_id="s1")
    trace.record("tool_call", session_id="s1", name="read_file", is_error=False)
    trace.record("tool_call", session_id="s1", name="bash", is_error=True)
    trace.record("checkpoint_created", session_id="s1", checkpoint_id="c1")
    trace.record("checkpoint_restored", session_id="s1", checkpoint_id="c1")
    trace.record(
        "model_response",
        session_id="s1",
        usage={"input_tokens": 10, "output_tokens": 5},
        cost_usd=0.000123,
    )
    trace.record("turn_end", session_id="s1", stop_reason="final_answer")

    summary = TraceRecorder(path).summary()

    assert summary["events"] == 7
    assert summary["tool_calls"] == 2
    assert summary["tool_errors"] == 1
    assert summary["checkpoints"] == 1
    assert summary["checkpoint_restores"] == 1
    assert summary["turns"] == 1
    assert summary["total_tokens"] == 15
    assert summary["cost_usd_micros"] == 123


def test_trace_query_filters_by_session_type_and_limit(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(path)
    trace.record("turn_start", session_id="s1")
    trace.record("tool_call", session_id="s1", name="read_file", is_error=False)
    trace.record("tool_call", session_id="s2", name="bash", is_error=True)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer")

    events = TraceQuery(TraceRecorder(path)).events(session_id="s1", event_type="tool_call", limit=1)
    summary = TraceQuery(TraceRecorder(path)).summary(session_id="s1")

    assert len(events) == 1
    assert events[0]["name"] == "read_file"
    assert summary["events"] == 3
    assert summary["tool_errors"] == 0


def test_trace_query_summarizes_sessions(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(path)
    trace.record("turn_start", session_id="s1")
    trace.record("model_response", session_id="s1", usage={"total_tokens": 7}, cost_usd=0.001)
    trace.record("tool_call", session_id="s1", name="read_file", is_error=False)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="done")
    trace.record("turn_start", session_id="s2")
    trace.record("tool_call", session_id="s2", name="bash", is_error=True)
    trace.record("turn_end", session_id="s2", stop_reason="max_iterations", final_text="")

    sessions = TraceQuery(TraceRecorder(path)).sessions()

    assert [session["session_id"] for session in sessions] == ["s1", "s2"]
    assert sessions[0]["stop_reason"] == "final_answer"
    assert sessions[0]["tool_errors"] == 0
    assert sessions[0]["total_tokens"] == 7
    assert sessions[0]["cost_usd"] == 0.001
    assert sessions[1]["tool_errors"] == 1


def test_cli_trace_and_doctor_commands(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    TraceRecorder(trace).record("turn_end", session_id="s1", stop_reason="final_answer")

    trace_result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "trace", "--trace", str(trace)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "events: 1" in trace_result.stdout

    doctor_result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "doctor", "--workspace", str(tmp_path / "ws")],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "workspace:" in doctor_result.stdout
    assert "tools: ok - 12 tools registered" in doctor_result.stdout


def test_cli_trace_can_filter_and_emit_json(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    recorder = TraceRecorder(trace)
    recorder.record("tool_call", session_id="s1", name="read_file", is_error=False)
    recorder.record("tool_call", session_id="s2", name="bash", is_error=True)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "trace",
            "--trace",
            str(trace),
            "--session",
            "s1",
            "--type",
            "tool_call",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert '"session_id": "s1"' in result.stdout
    assert '"session_id": "s2"' not in result.stdout


def test_cli_trace_sessions_summary(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    recorder = TraceRecorder(trace)
    recorder.record("turn_start", session_id="s1")
    recorder.record("tool_call", session_id="s1", name="read_file", is_error=False)
    recorder.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="ok")
    recorder.record("turn_start", session_id="s2")
    recorder.record("tool_call", session_id="s2", name="bash", is_error=True)
    recorder.record("turn_end", session_id="s2", stop_reason="tool_error", final_text="")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "trace",
            "--trace",
            str(trace),
            "--sessions",
            "--failures-only",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "s1" not in result.stdout
    assert "s2 tool_error" in result.stdout
    assert "tool_errors=1" in result.stdout


def test_cli_eval_command_passes_and_fails(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    recorder = TraceRecorder(trace)
    recorder.record("tool_call", session_id="s1", name="grep", is_error=False)
    recorder.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="ok")

    passed = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "eval",
            "--trace",
            str(trace),
            "--expect-stop-reason",
            "final_answer",
            "--require-tool",
            "grep",
            "--max-tool-errors",
            "0",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert passed.returncode == 0
    assert "passed: True" in passed.stdout

    failed = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "eval",
            "--trace",
            str(trace),
            "--require-tool",
            "bash",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert failed.returncode == 1
    assert "passed: False" in failed.stdout


def test_cli_replay_prints_trace_timeline(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    recorder = TraceRecorder(trace)
    recorder.record("turn_start", session_id="s1", user_input="hi")
    recorder.record("tool_call", session_id="s1", name="read_file", is_error=False)
    recorder.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="done")

    result = subprocess.run(
        [sys.executable, "-m", "harness.cli", "replay", "--trace", str(trace), "--session", "s1"],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "turn_start" in result.stdout
    assert "tool_call read_file ok" in result.stdout
    assert "turn_end final_answer" in result.stdout
