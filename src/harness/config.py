from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfigIssue:
    level: str
    key: str
    message: str


@dataclass
class HarnessConfig:
    workspace: str = ".harness/workspace"
    session_dir: str = ".harness/sessions"
    trace: str = ".harness/trace.jsonl"
    audit: str = ".harness/audit.jsonl"
    artifact_dir: str = ".harness/artifacts"
    memory_dir: str = ".harness/memory"
    skill_dir: str = ".harness/skills"
    task_dir: str = ".harness/tasks"
    hook_config: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str = "gpt-4.1-mini"
    permission: str = "read-only"
    allowed_tools: list[str] | None = None
    denied_tools: list[str] | None = None
    max_output_chars: int = 20_000
    max_file_read_bytes: int = 1_000_000
    default_bash_timeout_seconds: int = 30
    max_bash_timeout_seconds: int = 120
    max_iterations: int = 20
    max_model_retries: int = 0
    input_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float = 0.0
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> "HarnessConfig":
        data: dict[str, Any] = {}
        if path:
            config_path = Path(path).expanduser()
            if config_path.exists():
                data = json.loads(config_path.read_text(encoding="utf-8"))
        config = cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})
        config.apply_env()
        return config

    def apply_env(self) -> None:
        mapping = {
            "HARNESS_WORKSPACE": "workspace",
            "HARNESS_SESSION_DIR": "session_dir",
            "HARNESS_TRACE": "trace",
            "HARNESS_AUDIT": "audit",
            "HARNESS_ARTIFACT_DIR": "artifact_dir",
            "HARNESS_MEMORY_DIR": "memory_dir",
            "HARNESS_SKILL_DIR": "skill_dir",
            "HARNESS_TASK_DIR": "task_dir",
            "HARNESS_HOOK_CONFIG": "hook_config",
            "HARNESS_BASE_URL": "base_url",
            "OPENAI_BASE_URL": "base_url",
            "HARNESS_API_KEY": "api_key",
            "OPENAI_API_KEY": "api_key",
            "HARNESS_MODEL": "model",
            "HARNESS_PERMISSION": "permission",
            "HARNESS_ALLOWED_TOOLS": "allowed_tools",
            "HARNESS_DENIED_TOOLS": "denied_tools",
            "HARNESS_MAX_OUTPUT_CHARS": "max_output_chars",
            "HARNESS_MAX_FILE_READ_BYTES": "max_file_read_bytes",
            "HARNESS_DEFAULT_BASH_TIMEOUT_SECONDS": "default_bash_timeout_seconds",
            "HARNESS_MAX_BASH_TIMEOUT_SECONDS": "max_bash_timeout_seconds",
            "HARNESS_MAX_ITERATIONS": "max_iterations",
            "HARNESS_MAX_MODEL_RETRIES": "max_model_retries",
            "HARNESS_INPUT_COST_PER_MILLION_TOKENS": "input_cost_per_million_tokens",
            "HARNESS_OUTPUT_COST_PER_MILLION_TOKENS": "output_cost_per_million_tokens",
            "HARNESS_MAX_TOTAL_TOKENS": "max_total_tokens",
            "HARNESS_MAX_COST_USD": "max_cost_usd",
        }
        for env_name, attr in mapping.items():
            value = os.environ.get(env_name)
            if value is None:
                continue
            if attr in {
                "max_iterations",
                "max_output_chars",
                "max_file_read_bytes",
                "default_bash_timeout_seconds",
                "max_bash_timeout_seconds",
                "max_total_tokens",
                "max_model_retries",
            }:
                setattr(self, attr, int(value))
            elif attr in {
                "input_cost_per_million_tokens",
                "output_cost_per_million_tokens",
                "max_cost_usd",
            }:
                setattr(self, attr, float(value))
            elif attr in {"allowed_tools", "denied_tools"}:
                setattr(self, attr, [item.strip() for item in value.split(",") if item.strip()])
            else:
                setattr(self, attr, value)

    def redacted_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("api_key"):
            data["api_key"] = "***"
        return data

    def validate(self) -> list[ConfigIssue]:
        issues: list[ConfigIssue] = []
        if self.permission not in {"read-only", "workspace-write", "danger", "prompt"}:
            issues.append(ConfigIssue("error", "permission", f"unknown permission: {self.permission}"))
        issues.extend(
            _check_minimum(
                {
                    "max_output_chars": (self.max_output_chars, 0),
                    "max_file_read_bytes": (self.max_file_read_bytes, 0),
                    "default_bash_timeout_seconds": (self.default_bash_timeout_seconds, 1),
                    "max_bash_timeout_seconds": (self.max_bash_timeout_seconds, 1),
                    "max_iterations": (self.max_iterations, 1),
                    "max_model_retries": (self.max_model_retries, 0),
                    "input_cost_per_million_tokens": (self.input_cost_per_million_tokens, 0),
                    "output_cost_per_million_tokens": (self.output_cost_per_million_tokens, 0),
                }
            )
        )
        if self.max_total_tokens is not None and self.max_total_tokens < 0:
            issues.append(ConfigIssue("error", "max_total_tokens", "must be greater than or equal to 0"))
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            issues.append(ConfigIssue("error", "max_cost_usd", "must be greater than or equal to 0"))
        if self.max_bash_timeout_seconds < self.default_bash_timeout_seconds:
            issues.append(
                ConfigIssue(
                    "error",
                    "max_bash_timeout_seconds",
                    "must be greater than or equal to default_bash_timeout_seconds",
                )
            )
        if bool(self.base_url) != bool(self.api_key):
            issues.append(ConfigIssue("warn", "model_endpoint", "base_url and api_key should be configured together"))
        allowed = set(self.allowed_tools or [])
        denied = set(self.denied_tools or [])
        overlap = sorted(allowed & denied)
        if overlap:
            issues.append(
                ConfigIssue("error", "tools", f"tools cannot be both allowed and denied: {', '.join(overlap)}")
            )
        return issues


def _check_minimum(values: dict[str, tuple[int | float, int | float]]) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    for key, (value, minimum) in values.items():
        if value < minimum:
            issues.append(ConfigIssue("error", key, f"must be greater than or equal to {minimum}"))
    return issues
