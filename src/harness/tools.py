from __future__ import annotations

import fnmatch
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.permissions import PermissionMode, Policy
from harness.workspace import Workspace


DEFAULT_MAX_OUTPUT_CHARS = 20_000
DEFAULT_MAX_FILE_READ_BYTES = 1_000_000
DEFAULT_BASH_TIMEOUT_SECONDS = 30
DEFAULT_MAX_BASH_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class ToolResult:
    output: str
    is_error: bool = False


ToolHandler = Callable[[dict[str, Any], Workspace], ToolResult]


@dataclass(frozen=True)
class ToolRuntimeLimits:
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    max_file_read_bytes: int = DEFAULT_MAX_FILE_READ_BYTES
    default_bash_timeout_seconds: int = DEFAULT_BASH_TIMEOUT_SECONDS
    max_bash_timeout_seconds: int = DEFAULT_MAX_BASH_TIMEOUT_SECONDS


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    required_permission: PermissionMode = PermissionMode.READ_ONLY
    max_output_chars: int = 20_000

    def run(self, arguments: dict[str, Any], workspace: Workspace, policy: Policy) -> ToolResult:
        decision = policy.check(self.name, self.required_permission)
        if not decision.allowed:
            return ToolResult(decision.reason, is_error=True)
        validation_error = self._validate_arguments(arguments)
        if validation_error:
            return ToolResult(validation_error, is_error=True)
        try:
            return self._limit(self.handler(arguments, workspace))
        except Exception as exc:  # noqa: BLE001 - tool errors should return to model.
            return ToolResult(str(exc), is_error=True)

    def _validate_arguments(self, arguments: Any) -> str:
        if not isinstance(arguments, dict):
            return "tool arguments must be an object"
        required = self.parameters.get("required") or []
        for name in required:
            if name not in arguments:
                return f"missing required argument: {name}"
        properties = self.parameters.get("properties") or {}
        for name, value in arguments.items():
            schema = properties.get(name)
            if not schema:
                continue
            expected_type = schema.get("type")
            if expected_type == "string" and not isinstance(value, str):
                return f"argument {name} must be string"
            if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                return f"argument {name} must be integer"
            if expected_type == "boolean" and not isinstance(value, bool):
                return f"argument {name} must be boolean"
        return ""

    def _limit(self, result: ToolResult) -> ToolResult:
        if self.max_output_chars <= 0 or len(result.output) <= self.max_output_chars:
            return result
        kept = result.output[: self.max_output_chars]
        suffix = f"\n[truncated {len(result.output) - self.max_output_chars} chars]"
        return ToolResult(kept + suffix, is_error=result.is_error)

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "required_permission": self.required_permission.value,
        }

    def openai_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition() for tool in self._tools.values()]

    def describe(self, name: str) -> dict[str, Any]:
        return self.get(name).definition()

    def openai_definitions(self) -> list[dict[str, Any]]:
        return [tool.openai_definition() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return sorted(self._tools)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _list_files(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    base = workspace.resolve(args.get("path") or ".")
    pattern = args.get("pattern") or "*"
    if not base.exists():
        return ToolResult(f"path does not exist: {base}", is_error=True)
    files: list[str] = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and fnmatch.fnmatch(path.name, pattern):
            files.append(str(path.relative_to(workspace.root)))
    return ToolResult("\n".join(files))


def _read_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    if not path.is_file():
        return ToolResult(f"not a file: {args['path']}", is_error=True)
    max_bytes = int(args.get("_max_file_read_bytes") or DEFAULT_MAX_FILE_READ_BYTES)
    size = path.stat().st_size
    if max_bytes > 0 and size > max_bytes:
        return ToolResult(
            f"file {args['path']} is {size} bytes and exceeds max_file_read_bytes={max_bytes}",
            is_error=True,
        )
    sample = path.read_bytes()
    if b"\x00" in sample[:8192]:
        return ToolResult(f"refusing to read binary file: {args['path']}", is_error=True)
    return ToolResult(path.read_text(encoding="utf-8"))


def _write_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(args.get("content", "")), encoding="utf-8")
    return ToolResult(f"wrote {path.relative_to(workspace.root)}")


def _edit_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    old = str(args["old"])
    new = str(args["new"])
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return ToolResult("old text not found", is_error=True)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return ToolResult(f"edited {path.relative_to(workspace.root)}")


def _move_path(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    source = workspace.resolve(args["source"])
    destination = workspace.resolve(args["destination"])
    if not source.exists():
        return ToolResult(f"source does not exist: {args['source']}", is_error=True)
    if destination.exists():
        return ToolResult(f"destination already exists: {args['destination']}", is_error=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return ToolResult(
        f"moved {source.relative_to(workspace.root)} to {destination.relative_to(workspace.root)}"
    )


def _delete_path(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    recursive = bool(args.get("recursive", False))
    if not path.exists():
        return ToolResult(f"path does not exist: {args['path']}", is_error=True)
    if path.is_dir():
        if recursive:
            shutil.rmtree(path)
        else:
            if any(path.iterdir()):
                return ToolResult(
                    "directory is not empty; pass recursive=true to delete it",
                    is_error=True,
                )
            path.rmdir()
    else:
        path.unlink()
    return ToolResult(f"deleted {path.relative_to(workspace.root)}")


def _grep(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    query = str(args["query"])
    base = workspace.resolve(args.get("path") or ".")
    matches: list[str] = []
    for path in sorted(base.rglob("*") if base.is_dir() else [base]):
        if not path.is_file():
            continue
        try:
            if b"\x00" in path.read_bytes()[:8192]:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if query in line:
                    matches.append(f"{path.relative_to(workspace.root)}:{lineno}:{line}")
        except UnicodeDecodeError:
            continue
    return ToolResult("\n".join(matches))


def _bash(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    command = str(args["command"])
    default_timeout = int(args.get("_default_bash_timeout_seconds") or DEFAULT_BASH_TIMEOUT_SECONDS)
    max_timeout = int(args.get("_max_bash_timeout_seconds") or DEFAULT_MAX_BASH_TIMEOUT_SECONDS)
    requested_timeout = int(args.get("timeout_seconds") or default_timeout)
    timeout = min(requested_timeout, max_timeout)
    try:
        completed = subprocess.run(
            command,
            cwd=workspace.root,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(f"command timed out after {timeout} seconds", True)
    output = completed.stdout
    if completed.stderr:
        output += ("\n" if output else "") + completed.stderr
    if completed.returncode != 0:
        return ToolResult(output or f"command failed with exit code {completed.returncode}", True)
    return ToolResult(output)


def _with_runtime_args(handler: ToolHandler, runtime_args: dict[str, Any]) -> ToolHandler:
    def wrapped(args: dict[str, Any], workspace: Workspace) -> ToolResult:
        merged = {**runtime_args, **args}
        return handler(merged, workspace)

    return wrapped


def default_tool_registry(
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    *,
    max_file_read_bytes: int = DEFAULT_MAX_FILE_READ_BYTES,
    default_bash_timeout_seconds: int = DEFAULT_BASH_TIMEOUT_SECONDS,
    max_bash_timeout_seconds: int = DEFAULT_MAX_BASH_TIMEOUT_SECONDS,
) -> ToolRegistry:
    limits = ToolRuntimeLimits(
        max_output_chars=max_output_chars,
        max_file_read_bytes=max_file_read_bytes,
        default_bash_timeout_seconds=default_bash_timeout_seconds,
        max_bash_timeout_seconds=max_bash_timeout_seconds,
    )
    read_handler = _with_runtime_args(
        _read_file,
        {"_max_file_read_bytes": limits.max_file_read_bytes},
    )
    bash_handler = _with_runtime_args(
        _bash,
        {
            "_default_bash_timeout_seconds": limits.default_bash_timeout_seconds,
            "_max_bash_timeout_seconds": limits.max_bash_timeout_seconds,
        },
    )
    registry = ToolRegistry()
    registry.register(
        Tool(
            "list_files",
            "List files under a workspace path.",
            _schema({"path": {"type": "string"}, "pattern": {"type": "string"}}, []),
            _list_files,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "read_file",
            "Read a UTF-8 file from the workspace.",
            _schema({"path": {"type": "string"}}, ["path"]),
            read_handler,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "write_file",
            "Write a UTF-8 file inside the workspace.",
            _schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
            _write_file,
            PermissionMode.WORKSPACE_WRITE,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "edit_file",
            "Replace the first occurrence of text in a workspace file.",
            _schema(
                {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
                ["path", "old", "new"],
            ),
            _edit_file,
            PermissionMode.WORKSPACE_WRITE,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "move_path",
            "Move or rename a file or directory inside the workspace.",
            _schema(
                {"source": {"type": "string"}, "destination": {"type": "string"}},
                ["source", "destination"],
            ),
            _move_path,
            PermissionMode.WORKSPACE_WRITE,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "delete_path",
            "Delete a file or directory inside the workspace.",
            _schema(
                {"path": {"type": "string"}, "recursive": {"type": "boolean"}},
                ["path"],
            ),
            _delete_path,
            PermissionMode.WORKSPACE_WRITE,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "grep",
            "Search for a literal string in workspace files.",
            _schema({"query": {"type": "string"}, "path": {"type": "string"}}, ["query"]),
            _grep,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "bash",
            "Run a shell command in the workspace.",
            _schema(
                {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}},
                ["command"],
            ),
            bash_handler,
            PermissionMode.DANGER,
            max_output_chars=limits.max_output_chars,
        )
    )
    return registry
