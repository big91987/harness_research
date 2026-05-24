from __future__ import annotations

import json
import os
import re
from pathlib import Path

from harness.config import HarnessConfig
from harness.storage import atomic_write_text


class SecretStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def set(self, name: str, value: str) -> None:
        if not value:
            raise ValueError("secret value must not be empty")
        data = self._load()
        data[_normalize_secret_name(name)] = value
        self._save(data)

    def get(self, name: str) -> str | None:
        return self._load().get(_normalize_secret_name(name))

    def delete(self, name: str) -> bool:
        data = self._load()
        key = _normalize_secret_name(name)
        if key not in data:
            return False
        del data[key]
        self._save(data)
        return True

    def list_names(self) -> list[str]:
        return sorted(self._load())

    def redacted_dict(self) -> dict[str, str]:
        return {name: "***" for name in self.list_names()}

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("secret store must contain a JSON object")
        result: dict[str, str] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, str):
                result[key] = value
        return result

    def _save(self, data: dict[str, str]) -> None:
        atomic_write_text(self.path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        if os.name == "posix":
            self.path.chmod(0o600)


def resolve_api_key(config: HarnessConfig, store: SecretStore | None = None) -> str | None:
    if config.api_key:
        return config.api_key
    if not config.api_key_secret:
        return None
    secret_store = store or SecretStore(config.secret_store)
    return secret_store.get(config.api_key_secret)


def _normalize_secret_name(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-")
    if not normalized:
        raise ValueError("secret name must contain at least one letter or number")
    return normalized
