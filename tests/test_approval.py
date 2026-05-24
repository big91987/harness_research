from harness.audit import AuditLog
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


def test_policy_denylist_wins_over_permission_mode() -> None:
    policy = Policy(PermissionMode.DANGER, denied_tools={"bash"})

    decision = policy.check("bash", PermissionMode.DANGER)

    assert not decision.allowed
    assert "denied by policy" in decision.reason


def test_policy_allowlist_restricts_tools() -> None:
    policy = Policy(PermissionMode.DANGER, allowed_tools={"read_file"})

    assert policy.check("read_file", PermissionMode.READ_ONLY).allowed
    denied = policy.check("write_file", PermissionMode.WORKSPACE_WRITE)
    assert not denied.allowed
    assert "not in allowed tools" in denied.reason


def test_prompt_policy_records_approval_audit(tmp_path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = Policy(
        PermissionMode.PROMPT,
        approval_callback=lambda action, required: False,
        audit=audit,
    )

    decision = policy.check("write_file", PermissionMode.WORKSPACE_WRITE)

    assert not decision.allowed
    event = audit.read_events()[0]
    assert event["type"] == "approval"
    assert event["action"] == "write_file"
    assert event["allowed"] is False


def test_policy_audit_records_context(tmp_path) -> None:
    audit = AuditLog(tmp_path / "audit.jsonl")
    policy = Policy(PermissionMode.READ_ONLY, audit=audit)

    decision = policy.check(
        "write_file",
        PermissionMode.WORKSPACE_WRITE,
        audit_context={"session_id": "s1", "turn_id": "t1"},
    )

    assert not decision.allowed
    event = audit.read_events()[0]
    assert event["type"] == "policy_denial"
    assert event["session_id"] == "s1"
    assert event["turn_id"] == "t1"
