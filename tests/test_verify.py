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
            run_live_tool_smoke=False,
            config=HarnessConfig(base_url="https://example.com", api_key="secret"),
        )
    )

    assert report.passed
    assert "live_smoke" not in report.results
    assert "live_tool_smoke" not in report.results


def test_verify_fails_invalid_config(tmp_path: Path) -> None:
    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_smoke=False,
            config=HarnessConfig(permission="invalid", max_iterations=0),
        )
    )

    assert not report.passed
    assert "config_validation" in report.results
    assert "permission" in report.results["config_validation"].output
    assert "max_iterations" in report.results["config_validation"].output


def test_verify_can_skip_config_validation(tmp_path: Path) -> None:
    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_smoke=False,
            run_config_validation=False,
            config=HarnessConfig(permission="invalid"),
        )
    )

    assert report.passed
    assert "config_validation" not in report.results


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


def test_live_tool_smoke_requires_created_file(tmp_path: Path, monkeypatch) -> None:
    def fake_run(name, command, cwd, env):  # noqa: ANN001 - test double matches private helper.
        return VerifyResult(name, True, "done\nsession: s1")

    monkeypatch.setattr(verify_module, "_run", fake_run)

    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_tool_smoke=True,
            config=HarnessConfig(base_url="https://example.com", api_key="secret"),
        )
    )

    assert not report.passed
    assert "live-tool-smoke.txt missing" in report.results["live_tool_smoke"].output


def test_live_tool_smoke_passes_when_model_created_file(tmp_path: Path, monkeypatch) -> None:
    def fake_run(name, command, cwd, env):  # noqa: ANN001 - test double matches private helper.
        workspace = Path(command[command.index("--workspace") + 1])
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "live-tool-smoke.txt").write_text("live-tool-smoke-ok", encoding="utf-8")
        return VerifyResult(name, True, "done\nsession: s1")

    monkeypatch.setattr(verify_module, "_run", fake_run)

    report = run_verify(
        VerifyOptions(
            root=Path.cwd(),
            work_dir=tmp_path,
            run_tests=False,
            run_compile=False,
            run_mock_smoke=False,
            run_live_tool_smoke=True,
            config=HarnessConfig(base_url="https://example.com", api_key="secret"),
        )
    )

    assert report.passed
    assert report.results["live_tool_smoke"].passed


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


def test_cli_verify_fails_invalid_config(tmp_path: Path) -> None:
    config = tmp_path / "harness.json"
    config.write_text('{"permission": "invalid"}', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--config",
            str(config),
            "verify",
            "--work-dir",
            str(tmp_path / "verify"),
            "--skip-tests",
            "--skip-compile",
            "--skip-mock-smoke",
        ],
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert result.returncode == 1
    assert "config_validation: failed" in result.stdout
    assert "permission" in result.stdout
