from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from harness.storage import atomic_write_text, file_lock


@dataclass(frozen=True)
class CacheEntry:
    namespace: str
    key_hash: str
    created_at: float
    expires_at: float | None
    path: Path


class FileCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def set(self, namespace: str, key: Any, value: Any, *, ttl_seconds: int | None = None) -> Path:
        path = self._path(namespace, key)
        expires_at = time() + ttl_seconds if ttl_seconds is not None else None
        payload = {
            "namespace": _normalize_namespace(namespace),
            "key": key,
            "key_hash": self.key_hash(key),
            "value": value,
            "created_at": time(),
            "expires_at": expires_at,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(self._lock_path(path)):
            atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return path

    def get(self, namespace: str, key: Any) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        with file_lock(self._lock_path(path)):
            payload = json.loads(path.read_text(encoding="utf-8"))
        if _is_expired(payload):
            return None
        return payload.get("value")

    def delete(self, namespace: str, key: Any) -> bool:
        path = self._path(namespace, key)
        if not path.exists():
            return False
        with file_lock(self._lock_path(path)):
            if path.exists():
                path.unlink()
        return True

    def clear(self, *, namespace: str | None = None) -> int:
        paths = list((self.root / _normalize_namespace(namespace)).glob("*.json")) if namespace else list(self.root.glob("*/*.json"))
        count = 0
        for path in paths:
            with file_lock(self._lock_path(path)):
                if path.exists():
                    path.unlink()
                    count += 1
        return count

    def list_entries(self, *, namespace: str | None = None) -> list[CacheEntry]:
        paths = list((self.root / _normalize_namespace(namespace)).glob("*.json")) if namespace else list(self.root.glob("*/*.json"))
        entries: list[CacheEntry] = []
        for path in sorted(paths):
            with file_lock(self._lock_path(path)):
                payload = json.loads(path.read_text(encoding="utf-8"))
            entries.append(
                CacheEntry(
                    namespace=str(payload.get("namespace") or path.parent.name),
                    key_hash=str(payload.get("key_hash") or path.stem),
                    created_at=float(payload.get("created_at") or 0.0),
                    expires_at=float(payload["expires_at"]) if payload.get("expires_at") is not None else None,
                    path=path,
                )
            )
        return entries

    def key_hash(self, key: Any) -> str:
        encoded = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _path(self, namespace: str, key: Any) -> Path:
        return self.root / _normalize_namespace(namespace) / f"{self.key_hash(key)}.json"

    def _lock_path(self, path: Path) -> Path:
        return path.with_name(f"{path.name}.lock")


def _is_expired(payload: dict[str, Any]) -> bool:
    expires_at = payload.get("expires_at")
    return expires_at is not None and float(expires_at) <= time()


def _normalize_namespace(namespace: str | None) -> str:
    value = (namespace or "default").strip().replace("/", "-")
    return value or "default"
