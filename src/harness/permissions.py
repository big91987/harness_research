from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from harness.audit import AuditLog


class PermissionMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER = "danger"
    PROMPT = "prompt"


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str = ""


ApprovalCallback = Callable[[str, PermissionMode], bool]


@dataclass
class Policy:
    mode: PermissionMode = PermissionMode.READ_ONLY
    approval_callback: ApprovalCallback | None = None
    allowed_tools: set[str] | None = None
    denied_tools: set[str] | None = None
    audit: AuditLog | None = None

    def check(
        self,
        action: str,
        required: PermissionMode,
        audit_context: dict[str, Any] | None = None,
    ) -> PermissionDecision:
        if self.denied_tools and action in self.denied_tools:
            decision = PermissionDecision(False, f"{action} denied by policy")
            self._audit_denial(action, required, decision.reason, audit_context)
            return decision
        if self.allowed_tools is not None and action not in self.allowed_tools:
            decision = PermissionDecision(False, f"{action} is not in allowed tools")
            self._audit_denial(action, required, decision.reason, audit_context)
            return decision
        if required == PermissionMode.READ_ONLY:
            return PermissionDecision(True)
        if self.mode == PermissionMode.DANGER:
            return PermissionDecision(True)
        if self.mode == PermissionMode.WORKSPACE_WRITE and required == PermissionMode.WORKSPACE_WRITE:
            return PermissionDecision(True)
        if self.mode == PermissionMode.PROMPT and self.approval_callback:
            allowed = self.approval_callback(action, required)
            self._audit_approval(action, required, allowed, audit_context)
            if allowed:
                return PermissionDecision(True)
            return PermissionDecision(False, f"{action} was denied by approval policy")
        decision = PermissionDecision(
            False,
            f"{action} requires {required.value} permission, current mode is {self.mode.value}",
        )
        self._audit_denial(action, required, decision.reason, audit_context)
        return decision

    def _audit_denial(
        self,
        action: str,
        required: PermissionMode,
        reason: str,
        audit_context: dict[str, Any] | None,
    ) -> None:
        if self.audit:
            self.audit.record(
                "policy_denial",
                **dict(audit_context or {}),
                actor="policy",
                action=action,
                required_permission=required.value,
                allowed=False,
                reason=reason,
            )

    def _audit_approval(
        self,
        action: str,
        required: PermissionMode,
        allowed: bool,
        audit_context: dict[str, Any] | None,
    ) -> None:
        if self.audit:
            self.audit.record(
                "approval",
                **dict(audit_context or {}),
                actor="user",
                action=action,
                required_permission=required.value,
                allowed=allowed,
            )
