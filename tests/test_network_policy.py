from __future__ import annotations

import pytest

from harness.network_policy import NetworkPolicy


def test_network_policy_allows_matching_hosts_and_rejects_others() -> None:
    policy = NetworkPolicy(allow_hosts=["api.deepseek.com", "*.example.com"])

    policy.check_url("https://api.deepseek.com/chat/completions")
    policy.check_url("https://model.example.com/v1")

    with pytest.raises(PermissionError) as exc:
        policy.check_url("https://evil.test/v1")

    assert "host is not allowed" in str(exc.value)


def test_network_policy_deny_hosts_take_precedence() -> None:
    policy = NetworkPolicy(allow_hosts=["*.example.com"], deny_hosts=["blocked.example.com"])

    with pytest.raises(PermissionError) as exc:
        policy.check_url("https://blocked.example.com/v1")

    assert "host is denied" in str(exc.value)


def test_network_policy_rejects_plain_http_by_default() -> None:
    policy = NetworkPolicy(allow_hosts=["api.example.com"])

    with pytest.raises(PermissionError) as exc:
        policy.check_url("http://api.example.com/v1")

    assert "scheme is not allowed" in str(exc.value)
