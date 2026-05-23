from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


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

    def check(self, action: str, required: PermissionMode) -> PermissionDecision:
        if required == PermissionMode.READ_ONLY:
            return PermissionDecision(True)
        if self.mode == PermissionMode.DANGER:
            return PermissionDecision(True)
        if self.mode == PermissionMode.WORKSPACE_WRITE and required == PermissionMode.WORKSPACE_WRITE:
            return PermissionDecision(True)
        if self.mode == PermissionMode.PROMPT and self.approval_callback:
            if self.approval_callback(action, required):
                return PermissionDecision(True)
            return PermissionDecision(False, f"{action} was denied by approval policy")
        return PermissionDecision(
            False,
            f"{action} requires {required.value} permission, current mode is {self.mode.value}",
        )

