from __future__ import annotations

import difflib
import fnmatch
import json
import shlex
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
TOOL_CATEGORY_FILESYSTEM = "filesystem"
TOOL_CATEGORY_SEARCH = "search"
TOOL_CATEGORY_EXECUTION = "execution"
TOOL_PROFILE_SAFE = "safe"
TOOL_PROFILE_CODING = "coding"
TOOL_PROFILES: dict[str, tuple[str, ...]] = {
    TOOL_PROFILE_SAFE: ("diff_file", "grep", "list_files", "read_file"),
    TOOL_PROFILE_CODING: (
        "append_file",
        "bash",
        "copy_path",
        "delete_path",
        "diff_file",
        "edit_file",
        "grep",
        "list_files",
        "make_directory",
        "move_path",
        "read_file",
        "write_file",
    ),
}


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
    sandbox_runner: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    required_permission: PermissionMode = PermissionMode.READ_ONLY
    max_output_chars: int = 20_000
    category: str = TOOL_CATEGORY_FILESYSTEM
    sandbox_required: bool = False

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
            if expected_type == "object" and not isinstance(value, dict):
                return f"argument {name} must be object"
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
            "category": self.category,
            "sandbox_required": self.sandbox_required,
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

    def filter_by_name(self, names: tuple[str, ...]) -> "ToolRegistry":
        filtered = ToolRegistry()
        for name in names:
            if name in self._tools:
                filtered.register(self._tools[name])
        return filtered


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _list_files(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    base = workspace.resolve(args.get("path") or ".")
    pattern = args.get("pattern") or "*"
    max_entries = int(args.get("max_entries") or 0)
    max_depth = int(args["max_depth"]) if "max_depth" in args else 0
    if max_entries < 0:
        return ToolResult("max_entries must be >= 0", is_error=True)
    if max_depth < 0:
        return ToolResult("max_depth must be >= 0", is_error=True)
    if not base.exists():
        return ToolResult(f"path does not exist: {base}", is_error=True)
    entries: list[str] = []
    truncated = False
    for path in sorted(base.rglob("*")):
        depth = len(path.relative_to(base).parts)
        if max_depth > 0 and depth > max_depth:
            continue
        if not fnmatch.fnmatch(path.name, pattern):
            continue
        suffix = "/" if path.is_dir() else ""
        entries.append(str(path.relative_to(workspace.root)) + suffix)
        if max_entries > 0 and len(entries) >= max_entries:
            truncated = True
            break
    if truncated:
        entries.append(f"[truncated after {max_entries} entries]")
    return ToolResult("\n".join(entries))


def _read_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    if not path.is_file():
        return ToolResult(f"not a file: {args['path']}", is_error=True)
    start_line = int(args["start_line"]) if "start_line" in args else 1
    max_lines = args.get("max_lines")
    if start_line < 1:
        return ToolResult("start_line must be >= 1", is_error=True)
    if max_lines is not None and int(max_lines) < 1:
        return ToolResult("max_lines must be >= 1", is_error=True)
    max_bytes = int(args.get("_max_file_read_bytes") or DEFAULT_MAX_FILE_READ_BYTES)
    size = path.stat().st_size
    range_read = "start_line" in args or "max_lines" in args
    if max_bytes > 0 and size > max_bytes and not range_read:
        return ToolResult(
            f"file {args['path']} is {size} bytes and exceeds max_file_read_bytes={max_bytes}",
            is_error=True,
        )
    sample = path.read_bytes()
    if b"\x00" in sample[:8192]:
        return ToolResult(f"refusing to read binary file: {args['path']}", is_error=True)
    if range_read:
        max_line_count = int(max_lines) if max_lines is not None else None
        return ToolResult(_read_line_range(path, start_line, max_line_count))
    return ToolResult(path.read_text(encoding="utf-8"))


def _read_line_range(path: Path, start_line: int, max_lines: int | None) -> str:
    selected: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if lineno < start_line:
                continue
            selected.append(line)
            if max_lines is not None and len(selected) >= max_lines:
                break
    return "".join(selected)


def _write_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(args.get("content", "")), encoding="utf-8")
    return ToolResult(f"wrote {path.relative_to(workspace.root)}")


def _append_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(str(args.get("content", "")))
    return ToolResult(f"appended {path.relative_to(workspace.root)}")


def _diff_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    old = str(args["old"])
    new = str(args["new"])
    replace_all = bool(args.get("replace_all", False))
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return ToolResult("old text not found", is_error=True)
    count = text.count(old) if replace_all else 1
    updated = text.replace(old, new, count)
    rel = path.relative_to(workspace.root).as_posix()
    diff = difflib.unified_diff(
        text.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=rel,
        tofile=rel,
    )
    return ToolResult("".join(diff))


def _edit_file(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    old = str(args["old"])
    new = str(args["new"])
    replace_all = bool(args.get("replace_all", False))
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return ToolResult("old text not found", is_error=True)
    count = text.count(old) if replace_all else 1
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    return ToolResult(f"edited {path.relative_to(workspace.root)} replacements: {count}")


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


def _make_directory(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    path = workspace.resolve(args["path"])
    path.mkdir(parents=True, exist_ok=True)
    return ToolResult(f"created directory {path.relative_to(workspace.root)}")


def _copy_path(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    source = workspace.resolve(args["source"])
    destination = workspace.resolve(args["destination"])
    if not source.exists():
        return ToolResult(f"source does not exist: {args['source']}", is_error=True)
    if destination.exists():
        return ToolResult(f"destination already exists: {args['destination']}", is_error=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return ToolResult(
        f"copied {source.relative_to(workspace.root)} to {destination.relative_to(workspace.root)}"
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
    pattern = args.get("pattern") or "*"
    max_matches = int(args.get("max_matches") or 0)
    context_lines = int(args.get("context_lines") or 0)
    case_sensitive = bool(args.get("case_sensitive", True))
    needle = query if case_sensitive else query.lower()
    if max_matches < 0:
        return ToolResult("max_matches must be >= 0", is_error=True)
    if context_lines < 0:
        return ToolResult("context_lines must be >= 0", is_error=True)
    matches: list[str] = []
    match_count = 0
    truncated = False
    for path in sorted(base.rglob("*") if base.is_dir() else [base]):
        if not path.is_file():
            continue
        if not fnmatch.fnmatch(path.name, pattern):
            continue
        try:
            if b"\x00" in path.read_bytes()[:8192]:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for lineno, line in enumerate(lines, start=1):
                haystack = line if case_sensitive else line.lower()
                if needle in haystack:
                    rel = path.relative_to(workspace.root)
                    for index in range(max(1, lineno - context_lines), lineno):
                        matches.append(f"{rel}:{index}-{lines[index - 1]}")
                    matches.append(f"{rel}:{lineno}:{line}")
                    for index in range(lineno + 1, min(len(lines), lineno + context_lines) + 1):
                        matches.append(f"{rel}:{index}-{lines[index - 1]}")
                    match_count += 1
                    if max_matches > 0 and match_count >= max_matches:
                        truncated = True
                        raise StopIteration
        except UnicodeDecodeError:
            continue
        except StopIteration:
            break
    if truncated:
        matches.append(f"[truncated after {max_matches} matches]")
    return ToolResult("\n".join(matches))


def _bash(args: dict[str, Any], workspace: Workspace) -> ToolResult:
    command = str(args["command"])
    cwd = workspace.resolve(args.get("cwd") or ".")
    if not cwd.is_dir():
        return ToolResult(f"cwd is not a directory: {args.get('cwd') or '.'}", is_error=True)
    extra_env = {str(key): str(value) for key, value in dict(args.get("env") or {}).items()}
    default_timeout = int(args.get("_default_bash_timeout_seconds") or DEFAULT_BASH_TIMEOUT_SECONDS)
    max_timeout = int(args.get("_max_bash_timeout_seconds") or DEFAULT_MAX_BASH_TIMEOUT_SECONDS)
    requested_timeout = int(args.get("timeout_seconds") or default_timeout)
    timeout = min(requested_timeout, max_timeout)
    runner = str(args.get("_sandbox_runner") or "").strip()
    if not runner:
        return ToolResult("sandbox runner is required for bash", is_error=True)
    request = {
        "tool": "bash",
        "command": command,
        "cwd": str(cwd),
        "workspace_root": str(workspace.root),
        "env": extra_env,
        "timeout_seconds": timeout,
    }
    try:
        completed = subprocess.run(
            shlex.split(runner),
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(f"sandbox runner timed out after {timeout} seconds", True)
    except FileNotFoundError:
        return ToolResult(f"sandbox runner not found: {runner}", True)
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
    sandbox_runner: str | None = None,
    tool_profile: str | None = None,
) -> ToolRegistry:
    limits = ToolRuntimeLimits(
        max_output_chars=max_output_chars,
        max_file_read_bytes=max_file_read_bytes,
        default_bash_timeout_seconds=default_bash_timeout_seconds,
        max_bash_timeout_seconds=max_bash_timeout_seconds,
        sandbox_runner=sandbox_runner,
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
            "_sandbox_runner": limits.sandbox_runner,
        },
    )
    registry = ToolRegistry()
    registry.register(
        Tool(
            "list_files",
            "List files under a workspace path.",
            _schema(
                {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                    "max_entries": {"type": "integer"},
                    "max_depth": {"type": "integer"},
                },
                [],
            ),
            _list_files,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "read_file",
            "Read a UTF-8 file from the workspace.",
            _schema(
                {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "max_lines": {"type": "integer"},
                },
                ["path"],
            ),
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
            "append_file",
            "Append UTF-8 content to a file inside the workspace.",
            _schema(
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
            ),
            _append_file,
            PermissionMode.WORKSPACE_WRITE,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "diff_file",
            "Preview a single text replacement in a workspace file as a unified diff.",
            _schema(
                {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
                ["path", "old", "new"],
            ),
            _diff_file,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "edit_file",
            "Replace the first occurrence of text in a workspace file.",
            _schema(
                {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
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
            "make_directory",
            "Create a directory inside the workspace.",
            _schema({"path": {"type": "string"}}, ["path"]),
            _make_directory,
            PermissionMode.WORKSPACE_WRITE,
            max_output_chars=limits.max_output_chars,
        )
    )
    registry.register(
        Tool(
            "copy_path",
            "Copy a file or directory inside the workspace.",
            _schema(
                {"source": {"type": "string"}, "destination": {"type": "string"}},
                ["source", "destination"],
            ),
            _copy_path,
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
            _schema(
                {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                    "max_matches": {"type": "integer"},
                    "context_lines": {"type": "integer"},
                    "case_sensitive": {"type": "boolean"},
                },
                ["query"],
            ),
            _grep,
            max_output_chars=limits.max_output_chars,
            category=TOOL_CATEGORY_SEARCH,
        )
    )
    registry.register(
        Tool(
            "bash",
            "Run a shell command in the workspace.",
            _schema(
                {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout_seconds": {"type": "integer"},
                    "env": {"type": "object"},
                },
                ["command"],
            ),
            bash_handler,
            PermissionMode.DANGER,
            max_output_chars=limits.max_output_chars,
            category=TOOL_CATEGORY_EXECUTION,
            sandbox_required=True,
        )
    )
    if tool_profile is None:
        return registry
    if tool_profile not in TOOL_PROFILES:
        raise ValueError(f"unknown tool profile: {tool_profile}")
    return registry.filter_by_name(TOOL_PROFILES[tool_profile])
