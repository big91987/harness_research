import os
import subprocess
import sys
from pathlib import Path

from harness.trace import TraceRecorder


def test_trace_recorder_summarizes_events(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    trace = TraceRecorder(path)
    trace.record("turn_start", session_id="s1")
    trace.record("tool_call", session_id="s1", name="read_file", is_error=False)
    trace.record("tool_call", session_id="s1", name="bash", is_error=True)
    trace.record("turn_end", session_id="s1", stop_reason="final_answer")

    summary = TraceRecorder(path).summary()

    assert summary["events"] == 4
    assert summary["tool_calls"] == 2
    assert summary["tool_errors"] == 1
    assert summary["turns"] == 1


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
    assert "tools: 6" in doctor_result.stdout


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
        [sys.executable, "-m", "harness.cli", "replay", "--trace", str(trace)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "turn_start" in result.stdout
    assert "tool_call read_file ok" in result.stdout
    assert "turn_end final_answer" in result.stdout
