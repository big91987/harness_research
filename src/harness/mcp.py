from __future__ import annotations

import json
import os
import select
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.tools import ToolResult


DEFAULT_MCP_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = DEFAULT_MCP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class McpToolSpec:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]


class McpProtocolError(RuntimeError):
    pass


def load_mcp_config(path: str | Path) -> list[McpServerConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError("mcp config must contain an object field: mcpServers")

    configs: list[McpServerConfig] = []
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            raise ValueError(f"mcp server config must be an object: {name}")
        command = raw.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError(f"mcp server requires command: {name}")
        args = raw.get("args", [])
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise ValueError(f"mcp server args must be a string list: {name}")
        env = raw.get("env", {})
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise ValueError(f"mcp server env must be a string map: {name}")
        timeout = raw.get("timeout_seconds", DEFAULT_MCP_TIMEOUT_SECONDS)
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError(f"mcp server timeout_seconds must be a positive integer: {name}")
        configs.append(McpServerConfig(name=name, command=command, args=args, env=env, timeout_seconds=timeout))
    return configs


class McpStdioClient:
    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._initialized = False

    def __enter__(self) -> McpStdioClient:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def start(self) -> None:
        if self.process is not None:
            return
        env = {**os.environ, **self.config.env}
        self.process = subprocess.Popen(
            [self.config.command, *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

    def close(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
        self.process = None
        self._initialized = False

    def initialize(self) -> dict[str, Any]:
        if self._initialized:
            return {}
        result = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "harness-research", "version": "0.1"},
            },
        )
        self._initialized = True
        return result

    def list_tools(self) -> list[McpToolSpec]:
        self.initialize()
        result = self._request("tools/list", {})
        raw_tools = result.get("tools", [])
        if not isinstance(raw_tools, list):
            raise McpProtocolError("tools/list result must contain a tools array")
        tools: list[McpToolSpec] = []
        for raw in raw_tools:
            if not isinstance(raw, dict):
                raise McpProtocolError("mcp tool must be an object")
            name = raw.get("name")
            if not isinstance(name, str) or not name:
                raise McpProtocolError("mcp tool requires name")
            description = raw.get("description", "")
            input_schema = raw.get("inputSchema", {})
            if not isinstance(description, str):
                raise McpProtocolError(f"mcp tool description must be string: {name}")
            if not isinstance(input_schema, dict):
                raise McpProtocolError(f"mcp tool inputSchema must be object: {name}")
            tools.append(
                McpToolSpec(
                    server=self.config.name,
                    name=name,
                    description=description,
                    input_schema=input_schema,
                )
            )
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        self.initialize()
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        output = _content_to_text(result.get("content", []))
        return ToolResult(output, is_error=bool(result.get("isError")))

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        process = self._require_process()
        request_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert process.stdin is not None
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        response = self._read_response(request_id)
        if "error" in response:
            error = response["error"]
            if isinstance(error, dict):
                raise McpProtocolError(str(error.get("message", error)))
            raise McpProtocolError(str(error))
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise McpProtocolError("mcp response result must be an object")
        return result

    def _read_response(self, request_id: int) -> dict[str, Any]:
        process = self._require_process()
        assert process.stdout is not None
        while True:
            ready, _, _ = select.select([process.stdout], [], [], self.config.timeout_seconds)
            if not ready:
                raise TimeoutError(f"mcp server timed out: {self.config.name}")
            line = process.stdout.readline()
            if line == "":
                stderr = ""
                if process.stderr is not None:
                    stderr = process.stderr.read()
                raise McpProtocolError(f"mcp server exited before response: {stderr.strip()}")
            response = json.loads(line)
            if response.get("id") == request_id:
                return response

    def _require_process(self) -> subprocess.Popen[str]:
        if self.process is None:
            self.start()
        assert self.process is not None
        if self.process.poll() is not None:
            raise McpProtocolError(f"mcp server is not running: {self.config.name}")
        return self.process


def list_mcp_tools(configs: list[McpServerConfig]) -> list[McpToolSpec]:
    tools: list[McpToolSpec] = []
    for config in configs:
        with McpStdioClient(config) as client:
            tools.extend(client.list_tools())
    return tools


def _content_to_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)
