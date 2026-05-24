from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from harness.kernel import AgentKernel
from harness.mcp import McpServerConfig, McpStdioClient, load_mcp_config, register_mcp_tools
from harness.model import FakeModelClient
from harness.permissions import PermissionMode, Policy
from harness.schema import ModelResponse, ToolCall
from harness.session import JsonlSessionStore, Session
from harness.tools import ToolRegistry
from harness.workspace import Workspace


def _write_mcp_server(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import json
import sys


TOOLS = [
    {
        "name": "echo",
        "description": "Echo text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }
]


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test-mcp", "version": "0.1"},
                },
            }
        )
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        args = request.get("params", {}).get("arguments", {})
        send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": f"echo: {args.get('text', '')}"}]},
            }
        )
    else:
        send({"jsonrpc": "2.0", "id": request_id, "error": {"message": f"unknown method: {method}"}})
""".lstrip(),
        encoding="utf-8",
    )


def test_mcp_config_loads_claude_style_servers(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": {
                        "command": sys.executable,
                        "args": ["server.py"],
                        "env": {"MCP_TEST": "1"},
                        "timeout_seconds": 3,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    configs = load_mcp_config(config_path)

    assert configs == [
        McpServerConfig(
            name="local",
            command=sys.executable,
            args=["server.py"],
            env={"MCP_TEST": "1"},
            timeout_seconds=3,
        )
    ]


def test_mcp_stdio_client_lists_and_calls_tools(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    _write_mcp_server(server)

    with McpStdioClient(McpServerConfig("local", sys.executable, [str(server)])) as client:
        tools = client.list_tools()
        result = client.call_tool("echo", {"text": "hello"})

    assert [tool.name for tool in tools] == ["echo"]
    assert tools[0].input_schema["required"] == ["text"]
    assert result.output == "echo: hello"
    assert result.is_error is False


def test_cli_mcp_lists_tools_from_stdio_server(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    _write_mcp_server(server)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"local": {"command": sys.executable, "args": [str(server)]}}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "mcp",
            "--mcp-config",
            str(config_path),
            "--list-tools",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )

    payload = json.loads(result.stdout)
    assert payload == [
        {
            "server": "local",
            "name": "echo",
            "description": "Echo text back.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }
    ]


def test_mcp_runtime_tools_are_namespaced_and_policy_gated(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    _write_mcp_server(server)
    registry = ToolRegistry()

    register_mcp_tools(registry, [McpServerConfig("local", sys.executable, [str(server)])])

    assert registry.names() == ["mcp__local__echo"]
    description = registry.describe("mcp__local__echo")
    assert description["category"] == "mcp"
    assert description["required_permission"] == "danger"
    assert description["sandbox_required"] is True
    denied = registry.get("mcp__local__echo").run(
        {"text": "hello"},
        Workspace(tmp_path / "ws"),
        Policy(PermissionMode.READ_ONLY),
    )
    allowed = registry.get("mcp__local__echo").run(
        {"text": "hello"},
        Workspace(tmp_path / "ws"),
        Policy(PermissionMode.DANGER),
    )

    assert denied.is_error is True
    assert "requires danger" in denied.output
    assert allowed.output == "echo: hello"


def test_kernel_can_call_runtime_loaded_mcp_tool(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    _write_mcp_server(server)
    registry = ToolRegistry()
    register_mcp_tools(registry, [McpServerConfig("local", sys.executable, [str(server)])])
    model = FakeModelClient(
        [
            ModelResponse(
                content="calling mcp",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="mcp__local__echo",
                        arguments={"text": "hello"},
                    )
                ],
            ),
            ModelResponse(content="done"),
        ]
    )
    workspace = Workspace(tmp_path / "ws")
    kernel = AgentKernel(
        model=model,
        tools=registry,
        store=JsonlSessionStore(tmp_path / "sessions"),
        workspace=workspace,
        policy=Policy(PermissionMode.DANGER),
    )

    result = kernel.run_turn(Session.new(workspace=str(workspace.root)), "use mcp echo")

    assert result.stop_reason == "final_answer"
    assert result.final_text == "done"
    assert model.calls[1][-1].content == "echo: hello"


def test_cli_run_can_load_mcp_tools_for_agent_runtime(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    _write_mcp_server(server)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"local": {"command": sys.executable, "args": [str(server)]}}}),
        encoding="utf-8",
    )
    script = tmp_path / "responses.json"
    script.write_text(
        json.dumps(
            [
                {
                    "content": "calling mcp",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "mcp__local__echo",
                            "arguments": {"text": "hello"},
                        }
                    ],
                },
                {"content": "done"},
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "run",
            "use mcp echo",
            "--workspace",
            str(tmp_path / "ws"),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--mcp-config",
            str(config_path),
            "--permission",
            "danger",
            "--mock-responses",
            str(script),
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )

    assert "done" in result.stdout
