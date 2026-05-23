from harness.model import OpenAICompatibleModelClient
from harness.schema import Message
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

