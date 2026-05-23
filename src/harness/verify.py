from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from harness.config import HarnessConfig


@dataclass(frozen=True)
class VerifyOptions:
    root: Path
    work_dir: Path
    run_tests: bool = True
    run_compile: bool = True
    run_mock_smoke: bool = True
    run_live_smoke: bool = False
    config: HarnessConfig = field(default_factory=HarnessConfig)


@dataclass(frozen=True)
class VerifyResult:
    name: str
    passed: bool
    output: str


@dataclass(frozen=True)
class VerifyReport:
    results: dict[str, VerifyResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results.values())


def run_verify(options: VerifyOptions) -> VerifyReport:
    root = options.root.resolve()
    work_dir = options.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    results: dict[str, VerifyResult] = {}

    if options.run_tests:
        results["pytest"] = _run("pytest", [sys.executable, "-m", "pytest"], root, env)

    if options.run_compile:
        compile_env = {**env, "PYTHONPYCACHEPREFIX": str(work_dir / "pycache")}
        results["compile"] = _run(
            "compile",
            [sys.executable, "-m", "compileall", "-q", "src"],
            root,
            compile_env,
        )

    if options.run_mock_smoke:
        results["mock_smoke"] = _run_mock_smoke(root, work_dir, env)

    if options.run_live_smoke:
        results["live_smoke"] = _run_live_smoke(root, work_dir, env, options.config)

    return VerifyReport(results)


def _run(name: str, command: list[str], cwd: Path, env: dict[str, str]) -> VerifyResult:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=False)
    output = completed.stdout + completed.stderr
    return VerifyResult(name, completed.returncode == 0, output)


def _run_mock_smoke(root: Path, work_dir: Path, env: dict[str, str]) -> VerifyResult:
    responses = work_dir / "mock_responses.json"
    workspace = work_dir / "workspace"
    trace = work_dir / "trace.jsonl"
    audit = work_dir / "audit.jsonl"
    responses.write_text(
        json.dumps(
            [
                {
                    "content": "writing file",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "write_file",
                            "arguments": {"path": "verify.txt", "content": "ok"},
                        }
                    ],
                },
                {"content": "created verify.txt"},
            ]
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "harness.cli",
        "run",
        "create verify file",
        "--workspace",
        str(workspace),
        "--session-dir",
        str(work_dir / "sessions"),
        "--trace",
        str(trace),
        "--audit",
        str(audit),
        "--permission",
        "workspace-write",
        "--mock-responses",
        str(responses),
    ]
    result = _run("mock_smoke", command, root, env)
    if result.passed and (workspace / "verify.txt").read_text(encoding="utf-8") != "ok":
        return VerifyResult("mock_smoke", False, result.output + "\nverify.txt content mismatch")
    return result


def _run_live_smoke(root: Path, work_dir: Path, env: dict[str, str], config: HarnessConfig) -> VerifyResult:
    if not config.base_url or not config.api_key:
        return VerifyResult("live_smoke", False, "missing base_url or api_key")
    live_env = {
        **env,
        "HARNESS_BASE_URL": config.base_url,
        "HARNESS_API_KEY": config.api_key,
        "HARNESS_MODEL": config.model,
        "HARNESS_MODEL_TIMEOUT_SECONDS": str(config.model_timeout_seconds),
    }
    command = [
        sys.executable,
        "-m",
        "harness.cli",
        "run",
        "Reply with the exact text: live-smoke-ok",
        "--workspace",
        str(work_dir / "live_workspace"),
        "--session-dir",
        str(work_dir / "live_sessions"),
        "--trace",
        str(work_dir / "live_trace.jsonl"),
        "--permission",
        "read-only",
        "--max-iterations",
        "1",
    ]
    result = _run("live_smoke", command, root, live_env)
    if result.passed and "live-smoke-ok" not in result.output:
        return VerifyResult("live_smoke", False, result.output + "\nexpected live-smoke-ok in output")
    return result
