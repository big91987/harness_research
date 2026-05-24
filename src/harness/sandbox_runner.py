from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_ENV_ALLOWLIST = {
    "HOME",
    "LANG",
    "LOGNAME",
    "PATH",
    "SHELL",
    "TERM",
    "TMPDIR",
    "USER",
}


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        return run_request(request)
    except Exception as exc:  # noqa: BLE001 - runner errors must be clear to the tool.
        print(f"sandbox runner error: {exc}", file=sys.stderr)
        return 2


def run_request(request: dict[str, Any]) -> int:
    tool = str(request.get("tool") or "")
    if tool != "bash":
        print(f"unsupported sandbox tool: {tool}", file=sys.stderr)
        return 2
    workspace = _resolve_existing_dir(str(request.get("workspace_root") or ""))
    cwd = _resolve_existing_dir(str(request.get("cwd") or workspace))
    if not _is_relative_to(cwd, workspace):
        print(f"cwd escapes workspace: {cwd}", file=sys.stderr)
        return 2
    timeout = int(request.get("timeout_seconds") or 30)
    if timeout < 1:
        print("timeout_seconds must be >= 1", file=sys.stderr)
        return 2
    env = _build_env(dict(request.get("env") or {}))
    try:
        sandbox_exec = _require_macos_sandbox()
        profile = _macos_sandbox_profile(workspace)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sb") as handle:
            handle.write(profile)
            handle.flush()
            completed = subprocess.run(
                [sandbox_exec, "-f", handle.name, "/bin/sh", "-c", str(request.get("command") or "")],
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=env,
                check=False,
            )
    except SandboxUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print(f"command timed out after {timeout} seconds", file=sys.stderr)
        return 124
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return int(completed.returncode)


class SandboxUnavailableError(RuntimeError):
    pass


def _require_macos_sandbox() -> str:
    if platform.system() != "Darwin":
        raise SandboxUnavailableError("macOS sandbox-exec is required for bash sandboxing")
    path = shutil.which("sandbox-exec")
    if not path:
        raise SandboxUnavailableError("sandbox-exec not found")
    return path


def _macos_sandbox_profile(workspace: Path) -> str:
    root = _escape_sandbox_string(str(workspace))
    sensitive_denies = "\n".join(
        f'(deny file-read-data (subpath "{_escape_sandbox_string(path)}"))'
        for path in _sensitive_read_paths()
    )
    return f"""
(version 1)
(deny default)
(allow process*)
(allow sysctl*)
(allow mach-lookup)
(allow file-read*)
{sensitive_denies}
(allow file-write* (subpath "{root}"))
(allow file-write* (literal "/dev/null"))
""".strip()


def _sensitive_read_paths() -> list[str]:
    home = Path.home()
    paths = [
        "/etc",
        "/private/etc",
        str(home / ".aws"),
        str(home / ".azure"),
        str(home / ".codex"),
        str(home / ".config"),
        str(home / ".docker"),
        str(home / ".gnupg"),
        str(home / ".hermes"),
        str(home / ".kube"),
        str(home / ".netrc"),
        str(home / ".npmrc"),
        str(home / ".ssh"),
    ]
    return sorted(set(paths))


def _escape_sandbox_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_env(extra: dict[str, Any]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in DEFAULT_ENV_ALLOWLIST or key.startswith("LC_"):
            env[key] = value
    env.setdefault("PATH", "/usr/bin:/bin")
    for key, value in extra.items():
        env[str(key)] = str(value)
    return env


def _resolve_existing_dir(raw: str) -> Path:
    if not raw:
        raise ValueError("path is required")
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"not a directory: {raw}")
    return path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
