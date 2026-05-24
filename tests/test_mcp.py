from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from harness.mcp import McpServerConfig, McpStdioClient, load_mcp_config


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
