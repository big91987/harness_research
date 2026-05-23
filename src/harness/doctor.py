from __future__ import annotations

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
        trace: str | Path,
        audit: str | Path,
        artifact_dir: str | Path,
        base_url: str | None,
        api_key: str | None,
        tools_count: int,
    ) -> "DoctorReport":
        checks: dict[str, DoctorCheck] = {}
        for name, raw_path, is_file in (
            ("workspace", workspace, False),
            ("session_dir", session_dir, False),
            ("memory_dir", memory_dir, False),
            ("trace", trace, True),
            ("audit", audit, True),
            ("artifact_dir", artifact_dir, False),
        ):
            checks[name] = _check_path(Path(raw_path).expanduser(), is_file=is_file)
        checks["tools"] = DoctorCheck(tools_count > 0, f"{tools_count} tools registered")
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

