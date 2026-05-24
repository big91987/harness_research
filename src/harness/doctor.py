from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DoctorCheck:
    ok: bool
    message: str
    level: str = "ok"


@dataclass(frozen=True)
class DoctorReport:
    checks: dict[str, DoctorCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok or check.level == "warn" for check in self.checks.values())

    @classmethod
    def build(
        cls,
        *,
        workspace: str | Path,
        session_dir: str | Path,
        memory_dir: str | Path,
        skill_dir: str | Path,
        task_dir: str | Path,
        run_dir: str | Path,
        trace: str | Path,
        audit: str | Path,
        artifact_dir: str | Path,
        base_url: str | None,
        api_key: str | None,
        tools_count: int,
        sandbox_runner: str | None = None,
    ) -> "DoctorReport":
        checks: dict[str, DoctorCheck] = {}
        for name, raw_path, is_file in (
            ("workspace", workspace, False),
            ("session_dir", session_dir, False),
            ("memory_dir", memory_dir, False),
            ("skill_dir", skill_dir, False),
            ("task_dir", task_dir, False),
            ("run_dir", run_dir, False),
            ("trace", trace, True),
            ("audit", audit, True),
            ("artifact_dir", artifact_dir, False),
        ):
            checks[name] = _check_path(Path(raw_path).expanduser(), is_file=is_file)
        checks["tools"] = DoctorCheck(tools_count > 0, f"{tools_count} tools registered")
        checks["sandbox_runner"] = _check_sandbox_runner(sandbox_runner, Path(workspace).expanduser())
        if base_url and api_key:
            checks["model_config"] = DoctorCheck(True, "model endpoint configured")
        else:
            checks["model_config"] = DoctorCheck(False, "missing base URL or api key", "warn")
        return cls(checks)


def _check_path(path: Path, *, is_file: bool) -> DoctorCheck:
    target = path.parent if is_file else path
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".harness_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return DoctorCheck(False, f"{path}: not writable: {exc}", "error")
    return DoctorCheck(True, f"{path}: writable")


def _check_sandbox_runner(runner: str | None, workspace: Path) -> DoctorCheck:
    if not runner:
        return DoctorCheck(False, "missing sandbox runner for high-risk tools", "warn")
    workspace.mkdir(parents=True, exist_ok=True)
    probe = workspace / ".harness_sandbox_probe"
    request = {
        "tool": "bash",
        "workspace_root": str(workspace.resolve()),
        "cwd": str(workspace.resolve()),
        "command": "printf ok > .harness_sandbox_probe && cat .harness_sandbox_probe",
        "timeout_seconds": 5,
    }
    try:
        completed = subprocess.run(
            shlex.split(runner),
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return DoctorCheck(False, f"sandbox runner not found: {runner}", "error")
    except subprocess.TimeoutExpired:
        return DoctorCheck(False, "sandbox runner probe timed out", "error")
    finally:
        probe.unlink(missing_ok=True)
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode != 0:
        return DoctorCheck(False, f"sandbox runner probe failed: {output}", "error")
    if completed.stdout != "ok":
        return DoctorCheck(False, f"sandbox runner probe returned unexpected output: {output}", "error")
    return DoctorCheck(True, "sandbox runner executed workspace probe")
