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
    memory_dir: str = ".harness/memory"
    base_url: str | None = None
    api_key: str | None = None
    model: str = "gpt-4.1-mini"
    permission: str = "read-only"
    max_iterations: int = 20

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
            "HARNESS_MEMORY_DIR": "memory_dir",
            "HARNESS_BASE_URL": "base_url",
            "OPENAI_BASE_URL": "base_url",
            "HARNESS_API_KEY": "api_key",
            "OPENAI_API_KEY": "api_key",
            "HARNESS_MODEL": "model",
            "HARNESS_PERMISSION": "permission",
            "HARNESS_MAX_ITERATIONS": "max_iterations",
        }
        for env_name, attr in mapping.items():
            value = os.environ.get(env_name)
            if value is None:
                continue
            if attr == "max_iterations":
                setattr(self, attr, int(value))
            else:
                setattr(self, attr, value)

    def redacted_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("api_key"):
            data["api_key"] = "***"
        return data

