from pathlib import Path

from harness.permissions import PermissionMode, Policy
from harness.tools import default_tool_registry
from harness.workspace import Workspace


def test_filesystem_tools_stay_inside_workspace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)

    write = tools.get("write_file")
    read = tools.get("read_file")

    result = write.run({"path": "notes/a.txt", "content": "hello"}, workspace, policy)
    assert not result.is_error
    assert (tmp_path / "notes" / "a.txt").read_text() == "hello"

    result = read.run({"path": "notes/a.txt"}, workspace, policy)
    assert result.output == "hello"

    escaped = write.run({"path": "../escape.txt", "content": "bad"}, workspace, policy)
    assert escaped.is_error
    assert "outside workspace" in escaped.output


def test_read_only_policy_denies_writes_but_allows_reads(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    (tmp_path / "a.txt").write_text("ok")
    tools = default_tool_registry()
    policy = Policy(PermissionMode.READ_ONLY)

    assert tools.get("read_file").run({"path": "a.txt"}, workspace, policy).output == "ok"
    denied = tools.get("write_file").run({"path": "b.txt", "content": "no"}, workspace, policy)
    assert denied.is_error
    assert "requires" in denied.output


def test_bash_requires_danger_permission(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    denied = tools.get("bash").run({"command": "pwd"}, workspace, Policy(PermissionMode.WORKSPACE_WRITE))
    assert denied.is_error

    allowed = tools.get("bash").run({"command": "printf ok"}, workspace, Policy(PermissionMode.DANGER))
    assert allowed.output == "ok"


def test_tool_output_is_truncated(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry(max_output_chars=10)
    (tmp_path / "long.txt").write_text("0123456789abcdef", encoding="utf-8")

    result = tools.get("read_file").run({"path": "long.txt"}, workspace, Policy(PermissionMode.READ_ONLY))

    assert result.output.startswith("0123456789")
    assert "truncated" in result.output


def test_read_file_rejects_files_over_size_limit(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry(max_file_read_bytes=4)
    (tmp_path / "large.txt").write_text("12345", encoding="utf-8")

    result = tools.get("read_file").run({"path": "large.txt"}, workspace, Policy(PermissionMode.READ_ONLY))

    assert result.is_error
    assert "exceeds max_file_read_bytes" in result.output


def test_read_file_rejects_binary_files(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")

    result = tools.get("read_file").run({"path": "bin.dat"}, workspace, Policy(PermissionMode.READ_ONLY))

    assert result.is_error
    assert "binary file" in result.output


def test_bash_timeout_is_clamped(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry(default_bash_timeout_seconds=1, max_bash_timeout_seconds=1)

    result = tools.get("bash").run(
        {"command": "python3 -c 'import time; time.sleep(2)'", "timeout_seconds": 99},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert result.is_error
    assert "timed out" in result.output


def test_tool_reports_missing_required_argument(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("read_file").run({}, workspace, Policy(PermissionMode.READ_ONLY))

    assert result.is_error
    assert "missing required argument: path" in result.output


def test_tool_reports_argument_type_errors(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("bash").run(
        {"command": "printf ok", "timeout_seconds": "slow"},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert result.is_error
    assert "argument timeout_seconds must be integer" in result.output


def test_tool_reports_non_object_arguments(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("list_files").run("not a dict", workspace, Policy(PermissionMode.READ_ONLY))

    assert result.is_error
    assert "tool arguments must be an object" in result.output


def test_tool_registry_describes_tools() -> None:
    registry = default_tool_registry()

    description = registry.describe("read_file")

    assert description["name"] == "read_file"
    assert description["required_permission"] == "read-only"
    assert description["parameters"]["required"] == ["path"]
