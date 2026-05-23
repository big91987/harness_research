from __future__ import annotations

import json
import os
import subprocess
import sys
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
        completed = subprocess.run(
            str(request.get("command") or ""),
            cwd=cwd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(f"command timed out after {timeout} seconds", file=sys.stderr)
        return 124
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return int(completed.returncode)


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
