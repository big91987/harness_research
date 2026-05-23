from pathlib import Path

from harness.permissions import PermissionMode, Policy
from harness.tools import default_tool_registry
from harness.workspace import Workspace


def _write_bash_runner(path: Path) -> str:
    path.write_text(
        """
import json
import subprocess
import sys

request = json.loads(sys.stdin.read())
completed = subprocess.run(
    request["command"],
    cwd=request["cwd"],
    shell=True,
    text=True,
    capture_output=True,
    timeout=request["timeout_seconds"],
    env={"PATH": "/usr/bin:/bin", **request.get("env", {})},
    check=False,
)
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
sys.exit(completed.returncode)
""".lstrip(),
        encoding="utf-8",
    )
    return f"python3 {path}"


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


def test_list_files_includes_directories_and_can_limit_entries(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir" / "nested.txt").write_text("nested", encoding="utf-8")
    (tmp_path / "root.txt").write_text("root", encoding="utf-8")

    result = tools.get("list_files").run(
        {"max_entries": 2},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert "dir/" in result.output
    assert "[truncated after 2 entries]" in result.output
    assert len([line for line in result.output.splitlines() if not line.startswith("[")]) == 2


def test_list_files_rejects_negative_max_entries(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("list_files").run(
        {"max_entries": -1},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert result.is_error
    assert "max_entries must be >= 0" in result.output


def test_list_files_can_limit_recursion_depth(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "dir" / "child").mkdir(parents=True)
    (tmp_path / "dir" / "child" / "nested.txt").write_text("nested", encoding="utf-8")
    (tmp_path / "root.txt").write_text("root", encoding="utf-8")

    result = tools.get("list_files").run(
        {"max_depth": 1},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert "dir/" in result.output
    assert "root.txt" in result.output
    assert "dir/child/" not in result.output
    assert "nested.txt" not in result.output


def test_list_files_rejects_negative_max_depth(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("list_files").run(
        {"max_depth": -1},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert result.is_error
    assert "max_depth must be >= 0" in result.output


def test_read_only_policy_denies_writes_but_allows_reads(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    (tmp_path / "a.txt").write_text("ok")
    tools = default_tool_registry()
    policy = Policy(PermissionMode.READ_ONLY)

    assert tools.get("read_file").run({"path": "a.txt"}, workspace, policy).output == "ok"
    denied = tools.get("write_file").run({"path": "b.txt", "content": "no"}, workspace, policy)
    assert denied.is_error
    assert "requires" in denied.output


def test_append_file_appends_to_existing_and_new_files(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)
    (tmp_path / "notes.txt").write_text("one\n", encoding="utf-8")

    existing = tools.get("append_file").run(
        {"path": "notes.txt", "content": "two\n"},
        workspace,
        policy,
    )
    new_file = tools.get("append_file").run(
        {"path": "nested/log.txt", "content": "created\n"},
        workspace,
        policy,
    )

    assert not existing.is_error
    assert not new_file.is_error
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "one\ntwo\n"
    assert (tmp_path / "nested" / "log.txt").read_text(encoding="utf-8") == "created\n"


def test_append_file_requires_workspace_write_permission(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("append_file").run(
        {"path": "notes.txt", "content": "no\n"},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert result.is_error
    assert "requires workspace-write permission" in result.output
    assert not (tmp_path / "notes.txt").exists()


def test_diff_file_previews_replacement_without_modifying_file(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = tools.get("diff_file").run(
        {"path": "notes.txt", "old": "two", "new": "TWO"},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert "--- notes.txt" in result.output
    assert "+++ notes.txt" in result.output
    assert "-two" in result.output
    assert "+TWO" in result.output
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "one\ntwo\nthree\n"


def test_diff_file_can_preview_all_replacements_when_requested(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "notes.txt").write_text("same\nsame\n", encoding="utf-8")

    result = tools.get("diff_file").run(
        {"path": "notes.txt", "old": "same", "new": "changed", "replace_all": True},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert result.output.count("-same") == 2
    assert result.output.count("+changed") == 2
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "same\nsame\n"


def test_diff_file_reports_missing_old_text(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "notes.txt").write_text("one\n", encoding="utf-8")

    result = tools.get("diff_file").run(
        {"path": "notes.txt", "old": "absent", "new": "value"},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert result.is_error
    assert "old text not found" in result.output


def test_edit_file_defaults_to_first_replacement(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "notes.txt").write_text("same\nsame\n", encoding="utf-8")

    result = tools.get("edit_file").run(
        {"path": "notes.txt", "old": "same", "new": "changed"},
        workspace,
        Policy(PermissionMode.WORKSPACE_WRITE),
    )

    assert not result.is_error
    assert "replacements: 1" in result.output
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "changed\nsame\n"


def test_edit_file_can_replace_all_matches_when_requested(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "notes.txt").write_text("same\nsame\n", encoding="utf-8")

    result = tools.get("edit_file").run(
        {"path": "notes.txt", "old": "same", "new": "changed", "replace_all": True},
        workspace,
        Policy(PermissionMode.WORKSPACE_WRITE),
    )

    assert not result.is_error
    assert "replacements: 2" in result.output
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "changed\nchanged\n"


def test_bash_requires_danger_permission(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    denied = tools.get("bash").run({"command": "pwd"}, workspace, Policy(PermissionMode.WORKSPACE_WRITE))
    assert denied.is_error

    allowed = tools.get("bash").run({"command": "printf ok"}, workspace, Policy(PermissionMode.DANGER))
    assert allowed.is_error
    assert "sandbox runner is required" in allowed.output


def test_bash_runs_through_configured_sandbox_runner(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    tools = default_tool_registry(sandbox_runner=_write_bash_runner(tmp_path / "runner.py"))

    result = tools.get("bash").run(
        {"command": "printf ok > out.txt && cat out.txt"},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert not result.is_error
    assert result.output == "ok"
    assert (tmp_path / "workspace" / "out.txt").read_text(encoding="utf-8") == "ok"


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


def test_make_directory_creates_nested_directories(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)

    result = tools.get("make_directory").run(
        {"path": "src/pkg"},
        workspace,
        policy,
    )

    assert not result.is_error
    assert "created directory src/pkg" in result.output
    assert (tmp_path / "src" / "pkg").is_dir()


def test_copy_path_copies_files_and_directories_inside_workspace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)
    (tmp_path / "source.txt").write_text("payload", encoding="utf-8")
    (tmp_path / "template").mkdir()
    (tmp_path / "template" / "a.txt").write_text("a", encoding="utf-8")

    file_result = tools.get("copy_path").run(
        {"source": "source.txt", "destination": "copies/source.txt"},
        workspace,
        policy,
    )
    dir_result = tools.get("copy_path").run(
        {"source": "template", "destination": "copies/template"},
        workspace,
        policy,
    )

    assert not file_result.is_error
    assert not dir_result.is_error
    assert "copied source.txt to copies/source.txt" in file_result.output
    assert (tmp_path / "copies" / "source.txt").read_text(encoding="utf-8") == "payload"
    assert (tmp_path / "copies" / "template" / "a.txt").read_text(encoding="utf-8") == "a"


def test_copy_path_refuses_existing_destination(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    policy = Policy(PermissionMode.WORKSPACE_WRITE)
    (tmp_path / "source.txt").write_text("payload", encoding="utf-8")
    (tmp_path / "dest.txt").write_text("existing", encoding="utf-8")

    result = tools.get("copy_path").run(
        {"source": "source.txt", "destination": "dest.txt"},
        workspace,
        policy,
    )

    assert result.is_error
    assert "destination already exists" in result.output
    assert (tmp_path / "dest.txt").read_text(encoding="utf-8") == "existing"


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


def test_grep_can_limit_matches(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "a.txt").write_text("needle one\nneedle two\nneedle three\n", encoding="utf-8")

    result = tools.get("grep").run(
        {"query": "needle", "max_matches": 2},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert "a.txt:1:needle one" in result.output
    assert "a.txt:2:needle two" in result.output
    assert "needle three" not in result.output
    assert "[truncated after 2 matches]" in result.output


def test_grep_can_include_context_lines(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "a.txt").write_text("before\nneedle\n after\n", encoding="utf-8")

    result = tools.get("grep").run(
        {"query": "needle", "context_lines": 1},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert not result.is_error
    assert "a.txt:1-before" in result.output
    assert "a.txt:2:needle" in result.output
    assert "a.txt:3- after" in result.output


def test_grep_can_ignore_case_when_requested(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "a.txt").write_text("Needle\n", encoding="utf-8")

    default_result = tools.get("grep").run(
        {"query": "needle"},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )
    insensitive_result = tools.get("grep").run(
        {"query": "needle", "case_sensitive": False},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert default_result.output == ""
    assert "a.txt:1:Needle" in insensitive_result.output


def test_grep_can_filter_by_file_name_pattern(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "a.md").write_text("needle\n", encoding="utf-8")

    result = tools.get("grep").run(
        {"query": "needle", "pattern": "*.py"},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert "a.py:1:needle" in result.output
    assert "a.md" not in result.output


def test_grep_rejects_negative_limits(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")

    max_result = tools.get("grep").run(
        {"query": "needle", "max_matches": -1},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )
    context_result = tools.get("grep").run(
        {"query": "needle", "context_lines": -1},
        workspace,
        Policy(PermissionMode.READ_ONLY),
    )

    assert max_result.is_error
    assert "max_matches must be >= 0" in max_result.output
    assert context_result.is_error
    assert "context_lines must be >= 0" in context_result.output


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
    tools = default_tool_registry(
        default_bash_timeout_seconds=1,
        max_bash_timeout_seconds=1,
        sandbox_runner=_write_bash_runner(tmp_path / "runner.py"),
    )

    result = tools.get("bash").run(
        {"command": "python3 -c 'import time; time.sleep(2)'", "timeout_seconds": 99},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert result.is_error
    assert "timed out" in result.output


def test_bash_accepts_structured_environment_variables(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry(sandbox_runner=_write_bash_runner(tmp_path / "runner.py"))

    result = tools.get("bash").run(
        {
            "command": "printf \"$HARNESS_TEST_VALUE\"",
            "env": {"HARNESS_TEST_VALUE": "from-env"},
        },
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert not result.is_error
    assert result.output == "from-env"


def test_bash_can_run_from_workspace_subdirectory(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry(sandbox_runner=_write_bash_runner(tmp_path / "runner.py"))
    (tmp_path / "pkg").mkdir()

    result = tools.get("bash").run(
        {"command": "pwd && printf ok > result.txt", "cwd": "pkg"},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert not result.is_error
    assert result.output.strip().endswith("/pkg")
    assert (tmp_path / "pkg" / "result.txt").read_text(encoding="utf-8") == "ok"


def test_bash_cwd_stays_inside_workspace(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("bash").run(
        {"command": "pwd", "cwd": ".."},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert result.is_error
    assert "outside workspace" in result.output


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


def test_tool_reports_object_argument_type_errors(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("bash").run(
        {"command": "printf ok", "env": "HARNESS_TEST_VALUE=x"},
        workspace,
        Policy(PermissionMode.DANGER),
    )

    assert result.is_error
    assert "argument env must be object" in result.output


def test_tool_reports_non_object_arguments(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    tools = default_tool_registry()

    result = tools.get("list_files").run("not a dict", workspace, Policy(PermissionMode.READ_ONLY))

    assert result.is_error
    assert "tool arguments must be an object" in result.output


def test_tool_registry_describes_tools() -> None:
    registry = default_tool_registry()

    read_description = registry.describe("read_file")
    append_description = registry.describe("append_file")
    diff_description = registry.describe("diff_file")
    delete_description = registry.describe("delete_path")

    assert read_description["name"] == "read_file"
    assert read_description["required_permission"] == "read-only"
    assert read_description["parameters"]["required"] == ["path"]
    assert "max_entries" in registry.describe("list_files")["parameters"]["properties"]
    assert "max_depth" in registry.describe("list_files")["parameters"]["properties"]
    assert append_description["name"] == "append_file"
    assert append_description["required_permission"] == "workspace-write"
    assert append_description["parameters"]["required"] == ["path", "content"]
    assert read_description["category"] == "filesystem"
    assert read_description["sandbox_required"] is False
    assert diff_description["name"] == "diff_file"
    assert diff_description["required_permission"] == "read-only"
    assert diff_description["parameters"]["required"] == ["path", "old", "new"]
    assert "replace_all" in diff_description["parameters"]["properties"]
    assert "replace_all" in registry.describe("edit_file")["parameters"]["properties"]
    assert registry.describe("make_directory")["required_permission"] == "workspace-write"
    assert registry.describe("copy_path")["parameters"]["required"] == ["source", "destination"]
    assert "max_matches" in registry.describe("grep")["parameters"]["properties"]
    assert "context_lines" in registry.describe("grep")["parameters"]["properties"]
    assert "case_sensitive" in registry.describe("grep")["parameters"]["properties"]
    assert "pattern" in registry.describe("grep")["parameters"]["properties"]
    assert registry.describe("bash")["category"] == "execution"
    assert registry.describe("bash")["sandbox_required"] is True
    assert delete_description["name"] == "delete_path"
    assert delete_description["required_permission"] == "workspace-write"
    assert delete_description["parameters"]["required"] == ["path"]


def test_tool_registry_can_apply_safe_profile() -> None:
    registry = default_tool_registry(tool_profile="safe")

    assert registry.names() == ["diff_file", "grep", "list_files", "read_file"]
    assert "bash" not in registry.names()
    assert "write_file" not in registry.names()


def test_tool_registry_can_apply_coding_profile() -> None:
    registry = default_tool_registry(tool_profile="coding")

    assert "bash" in registry.names()
    assert "write_file" in registry.names()
    assert "grep" in registry.names()


def test_tool_registry_rejects_unknown_profile() -> None:
    try:
        default_tool_registry(tool_profile="unknown")
    except ValueError as exc:
        assert "unknown tool profile" in str(exc)
    else:
        raise AssertionError("expected unknown profile to fail")
