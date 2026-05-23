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


def test_move_path_moves_files_inside_workspace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)
    (tmp_path / "src.txt").write_text("payload", encoding="utf-8")

    result = tools.get("move_path").run(
        {"source": "src.txt", "destination": "nested/dst.txt"},
        workspace,
        policy,
    )

    assert not result.is_error
    assert "moved src.txt to nested/dst.txt" in result.output
    assert not (tmp_path / "src.txt").exists()
    assert (tmp_path / "nested" / "dst.txt").read_text(encoding="utf-8") == "payload"


def test_delete_path_deletes_file_and_recursive_directory(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)
    (tmp_path / "old.txt").write_text("old", encoding="utf-8")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "nested.txt").write_text("nested", encoding="utf-8")

    file_result = tools.get("delete_path").run({"path": "old.txt"}, workspace, policy)
    dir_result = tools.get("delete_path").run(
        {"path": "dir", "recursive": True},
        workspace,
        policy,
    )

    assert not file_result.is_error
    assert not dir_result.is_error
    assert not (tmp_path / "old.txt").exists()
    assert not (tmp_path / "dir").exists()


def test_delete_path_refuses_nonempty_directory_without_recursive(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "nested.txt").write_text("nested", encoding="utf-8")

    result = tools.get("delete_path").run({"path": "dir"}, workspace, policy)

    assert result.is_error
    assert "directory is not empty" in result.output
    assert (tmp_path / "dir" / "nested.txt").exists()


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


def test_read_file_can_read_line_ranges_from_large_files(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry(max_file_read_bytes=8)
    (tmp_path / "large.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    result = tools.get("read_file").run(
        {"path": "large.txt", "start_line": 2, "max_lines": 2},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert result.output == "two\nthree\n"


def test_read_file_rejects_invalid_line_ranges(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")

    start_result = tools.get("read_file").run(
        {"path": "a.txt", "start_line": 0},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )
    max_result = tools.get("read_file").run(
        {"path": "a.txt", "max_lines": 0},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert start_result.is_error
    assert "start_line must be >= 1" in start_result.output
    assert max_result.is_error
    assert "max_lines must be >= 1" in max_result.output


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


def test_tool_reports_boolean_argument_type_errors(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("delete_path").run(
        {"path": "x", "recursive": "yes"},
        workspace,
        Policy(PermissionMode.WORKSPACE_WRITE),
    )

    assert result.is_error
    assert "argument recursive must be boolean" in result.output


def test_tool_reports_non_object_arguments(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("list_files").run("not a dict", workspace, Policy(PermissionMode.READ_ONLY))

    assert result.is_error
    assert "tool arguments must be an object" in result.output


def test_tool_registry_describes_tools() -> None:
    registry = default_tool_registry()

    read_description = registry.describe("read_file")
    delete_description = registry.describe("delete_path")

    assert read_description["name"] == "read_file"
    assert read_description["required_permission"] == "read-only"
    assert read_description["parameters"]["required"] == ["path"]
    assert delete_description["name"] == "delete_path"
    assert delete_description["required_permission"] == "workspace-write"
    assert delete_description["parameters"]["required"] == ["path"]
