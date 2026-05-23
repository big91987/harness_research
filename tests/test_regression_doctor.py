import json
import os
import subprocess
import sys
from pathlib import Path

from harness.doctor import DoctorReport
from harness.eval import EvalSuiteStore, run_golden_suite
from harness.trace import TraceRecorder


def test_run_golden_suite_evaluates_multiple_cases(tmp_path: Path) -> None:
    good_trace = tmp_path / "good.jsonl"
    bad_trace = tmp_path / "bad.jsonl"
    good = TraceRecorder(good_trace)
    good.record("tool_call", session_id="s1", name="write_file", is_error=False)
    good.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="ok")
    TraceRecorder(bad_trace).record("turn_end", session_id="s2", stop_reason="model_error")

    suite = tmp_path / "golden.json"
    suite.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "good",
                        "trace": str(good_trace),
                        "expect": {
                            "stop_reason": "final_answer",
                            "max_tool_errors": 0,
                            "required_tools": ["write_file"],
                            "final_text_contains": "ok",
                        },
                    },
                    {
                        "name": "bad",
                        "trace": str(bad_trace),
                        "expect": {"stop_reason": "final_answer"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = run_golden_suite(suite)

    assert not report.passed
    assert report.total == 2
    assert report.passed_count == 1
    assert report.cases[0].name == "good"
    assert report.cases[0].report.passed
    assert not report.cases[1].report.passed


def test_eval_suite_store_adds_and_lists_cases(tmp_path: Path) -> None:
    suite = tmp_path / "suite.json"
    store = EvalSuiteStore(suite)

    store.add_case(
        "smoke",
        trace="trace.jsonl",
        expect={
            "stop_reason": "final_answer",
            "required_tools": ["write_file"],
        },
    )

    cases = store.list_cases()
    assert cases[0]["name"] == "smoke"
    assert cases[0]["expect"]["required_tools"] == ["write_file"]


def test_doctor_report_checks_paths_and_model_config(tmp_path: Path) -> None:
    report = DoctorReport.build(
        workspace=tmp_path / "ws",
        session_dir=tmp_path / "sessions",
        memory_dir=tmp_path / "memory",
        skill_dir=tmp_path / "skills",
        task_dir=tmp_path / "tasks",
        trace=tmp_path / "trace.jsonl",
        audit=tmp_path / "audit.jsonl",
        artifact_dir=tmp_path / "artifacts",
        base_url=None,
        api_key=None,
        tools_count=6,
        sandbox_runner=None,
    )

    assert report.ok
    assert report.checks["workspace"].ok
    assert report.checks["skill_dir"].ok
    assert report.checks["task_dir"].ok
    assert report.checks["model_config"].ok is False
    assert "api key" in report.checks["model_config"].message
    assert report.checks["sandbox_runner"].level == "warn"


def test_cli_golden_and_doctor_commands(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    recorder = TraceRecorder(trace)
    recorder.record("tool_call", session_id="s1", name="grep", is_error=False)
    recorder.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="done")
    suite = tmp_path / "golden.json"
    suite.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "smoke",
                        "trace": str(trace),
                        "expect": {
                            "stop_reason": "final_answer",
                            "required_tools": ["grep"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    golden = subprocess.run(
        [sys.executable, "-m", "harness.cli", "golden", str(suite)],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "passed: True" in golden.stdout
    assert "smoke: passed" in golden.stdout

    doctor = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "doctor",
            "--workspace",
            str(tmp_path / "ws"),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--memory-dir",
            str(tmp_path / "memory"),
            "--skill-dir",
            str(tmp_path / "skills"),
            "--task-dir",
            str(tmp_path / "tasks"),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "workspace: ok" in doctor.stdout
    assert "skill_dir: ok" in doctor.stdout
    assert "task_dir: ok" in doctor.stdout
    assert "model_config: warn" in doctor.stdout
    assert "sandbox_runner: warn" in doctor.stdout


def test_cli_eval_suite_add_list_and_run(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    recorder = TraceRecorder(trace)
    recorder.record("tool_call", session_id="s1", name="grep", is_error=False)
    recorder.record("turn_end", session_id="s1", stop_reason="final_answer", final_text="done")
    suite = tmp_path / "suite.json"

    add = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "eval-suite",
            str(suite),
            "--add",
            "smoke",
            "--trace-path",
            str(trace),
            "--expect-stop-reason",
            "final_answer",
            "--require-tool",
            "grep",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "added: smoke" in add.stdout

    listing = subprocess.run(
        [sys.executable, "-m", "harness.cli", "eval-suite", str(suite), "--list"],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "smoke" in listing.stdout

    run = subprocess.run(
        [sys.executable, "-m", "harness.cli", "eval-suite", str(suite), "--run"],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert "passed: True" in run.stdout
