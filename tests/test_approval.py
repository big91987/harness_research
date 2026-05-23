from harness.permissions import PermissionMode, Policy


def test_prompt_policy_uses_approval_callback() -> None:
    asked: list[tuple[str, PermissionMode]] = []

    def approve(action: str, required: PermissionMode) -> bool:
        asked.append((action, required))
        return action == "write_file"

    policy = Policy(PermissionMode.PROMPT, approval_callback=approve)

    assert policy.check("write_file", PermissionMode.WORKSPACE_WRITE).allowed
    denied = policy.check("bash", PermissionMode.DANGER)

    assert not denied.allowed
    assert "denied" in denied.reason
    assert asked == [
        ("write_file", PermissionMode.WORKSPACE_WRITE),
        ("bash", PermissionMode.DANGER),
    ]

