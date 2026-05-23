import os
import subprocess
import sys
from pathlib import Path

from harness.config import HarnessConfig
from harness.verify import VerifyOptions, VerifyResult, run_verify
import harness.verify as verify_module


def test_verify_runner_quick_mode_runs_local_smoke(tmp_path: Path) -> None:
    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=True,
            run_live_smoke=False,
        )
    )

    assert report.passed
    assert report.results["mock_smoke"].passed


def test_live_smoke_is_skipped_without_opt_in(tmp_path: Path) -> None:
    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_smoke=False,
            config=HarnessConfig(base_url="https://example.com", api_key="secret"),
        )
    )

    assert report.passed
    assert "live_smoke" not in report.results


def test_live_smoke_requires_expected_text(tmp_path: Path, monkeypatch) -> None:
    def fake_run(name, command, cwd, env):  # noqa: ANN001 - test double matches private helper.
        return VerifyResult(name, True, "model said something else")

    monkeypatch.setattr(verify_module, "_run", fake_run)

    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_smoke=True,
            config=HarnessConfig(base_url="https://example.com", api_key="secret"),
        )
    )

    assert not report.passed
    assert "expected live-smoke-ok" in report.results["live_smoke"].output


def test_live_smoke_passes_when_expected_text_is_present(tmp_path: Path, monkeypatch) -> None:
    def fake_run(name, command, cwd, env):  # noqa: ANN001 - test double matches private helper.
        return VerifyResult(name, True, "live-smoke-ok\nsession: s1")

    monkeypatch.setattr(verify_module, "_run", fake_run)

    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_smoke=True,
            config=HarnessConfig(base_url="https://example.com", api_key="secret"),
        )
    )

    assert report.passed
    assert report.results["live_smoke"].passed


def test_cli_verify_quick_smoke(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "verify",
            "--work-dir",
            str(tmp_path),
            "--skip-tests",
            "--skip-compile",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert "mock_smoke: passed" in result.stdout
    assert "overall: True" in result.stdout
