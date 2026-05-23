from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from harness.schema import Message, ModelResponse, ToolCall


class ModelClient:
    def generate(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        raise NotImplementedError


class ModelProtocolError(RuntimeError):
    pass


class FakeModelClient(ModelClient):
    def __init__(self, responses: Sequence[ModelResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[list[Message]] = []

    def generate(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        self.calls.append(list(messages))
        if not self.responses:
            return ModelResponse(content="No fake response configured.")
        return self.responses.pop(0)


@dataclass
class OpenAICompatibleModelClient(ModelClient):
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 120
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None

    def build_payload(self, messages: list[Message], tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._message_to_openai(message) for message in messages],
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if tools:
            payload["tools"] = [self._tool_to_openai(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        return payload

    def generate(self, messages: list[Message], tools: list[dict[str, Any]]) -> ModelResponse:
        payload = self.build_payload(messages, tools)
        url = self.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"model request failed: HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"model request failed: {exc.reason}") from exc
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        return ModelResponse(
            content=msg.get("content") or "",
            tool_calls=self._parse_tool_calls(msg.get("tool_calls") or []),
            usage=data.get("usage") or {},
            raw=data,
        )

    def _message_to_openai(self, message: Message) -> dict[str, Any]:
        if message.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "name": message.name,
                "content": message.content,
            }
        out: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            out["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return out

    def _tool_to_openai(self, tool: dict[str, Any]) -> dict[str, Any]:
        if tool.get("type") == "function":
            return tool
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
            },
        }

    def _parse_tool_calls(self, items: list[dict[str, Any]]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for item in items:
            function = item.get("function") or {}
            arguments = function.get("arguments") or "{}"
            if isinstance(arguments, str):
                try:
                    parsed_args = json.loads(arguments or "{}")
                except json.JSONDecodeError as exc:
                    name = function.get("name") or "<unknown>"
                    raise ModelProtocolError(f"invalid JSON arguments for tool {name}: {exc.msg}") from exc
            else:
                parsed_args = arguments
            if not isinstance(parsed_args, dict):
                name = function.get("name") or "<unknown>"
                raise ModelProtocolError(f"tool {name} arguments must be a JSON object")
            name = function.get("name")
            if not name:
                raise ModelProtocolError("tool call is missing function.name")
            call_id = item.get("id") or ToolCall.new(name, parsed_args).id
            calls.append(ToolCall(id=call_id, name=name, arguments=parsed_args))
        return calls
