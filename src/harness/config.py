from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class HarnessConfig:
    workspace: str = ".harness/workspace"
    session_dir: str = ".harness/sessions"
    trace: str = ".harness/trace.jsonl"
    audit: str = ".harness/audit.jsonl"
    artifact_dir: str = ".harness/artifacts"
    memory_dir: str = ".harness/memory"
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
