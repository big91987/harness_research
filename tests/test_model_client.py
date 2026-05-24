import pytest

from harness.model import ModelProtocolError, OpenAICompatibleModelClient
from harness.network_policy import NetworkPolicy
from harness.schema import Message, ToolCall
from harness.tools import default_tool_registry


def test_openai_client_builds_chat_payload_without_leaking_key() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://example.com",
        api_key="secret",
        model="test-model",
    )

    payload = client.build_payload([Message.user("hello")], default_tool_registry().definitions())

    assert payload["model"] == "test-model"
    assert payload["messages"][0] == {"role": "user", "content": "hello"}
    assert payload["tools"][0]["type"] == "function"
    assert "secret" not in str(payload)


def test_openai_client_includes_optional_generation_parameters() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://example.com",
        api_key="secret",
        model="test-model",
        temperature=0.2,
        top_p=0.9,
        max_tokens=512,
    )

    payload = client.build_payload([Message.user("hello")], [])

    assert payload["temperature"] == 0.2
    assert payload["top_p"] == 0.9
    assert payload["max_tokens"] == 512


def test_openai_client_reports_invalid_tool_arguments() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://example.com",
        api_key="secret",
        model="test-model",
    )

    with pytest.raises(ModelProtocolError) as exc:
        client._parse_tool_calls(
            [
                {
                    "id": "call-1",
                    "function": {"name": "write_file", "arguments": "{bad json"},
                }
            ]
        )

    assert "invalid JSON arguments" in str(exc.value)


def test_openai_client_accepts_missing_tool_call_id() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://example.com",
        api_key="secret",
        model="test-model",
    )

    calls = client._parse_tool_calls(
        [{"function": {"name": "read_file", "arguments": "{\"path\":\"a.txt\"}"}}]
    )

    assert calls[0].id.startswith("call_")
    assert calls[0].arguments == {"path": "a.txt"}


def test_openai_client_round_trips_reasoning_content_metadata() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://example.com",
        api_key="secret",
        model="test-model",
    )
    message = Message.assistant(
        "thinking with tool",
        metadata={"reasoning_content": "internal reasoning"},
    )

    payload = client.build_payload([message], [])

    assert payload["messages"][0]["reasoning_content"] == "internal reasoning"


def test_openai_client_parses_reasoning_content_from_response_message() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://example.com",
        api_key="secret",
        model="test-model",
    )
    response = client._response_from_data(
        {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": "must be echoed",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "write_file",
                                    "arguments": "{\"path\":\"a.txt\",\"content\":\"ok\"}",
                                },
                            }
                        ],
                    }
                }
            ]
        }
    )

    assert response.metadata["reasoning_content"] == "must be echoed"
    assert response.tool_calls == [ToolCall("call-1", "write_file", {"path": "a.txt", "content": "ok"})]


def test_openai_client_checks_network_policy_before_request() -> None:
    client = OpenAICompatibleModelClient(
        base_url="https://blocked.example.com",
        api_key="secret",
        model="test-model",
        network_policy=NetworkPolicy(allow_hosts=["api.example.com"]),
    )

    with pytest.raises(PermissionError) as exc:
        client.generate([Message.user("hello")], [])

    assert "host is not allowed" in str(exc.value)
