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
