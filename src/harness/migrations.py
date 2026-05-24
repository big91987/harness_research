from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.storage import atomic_write_text, file_lock


MigrationApply = Callable[[Path], None]


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationApply


@dataclass(frozen=True)
class MigrationReport:
    current_version: int
    pending: list[Migration]
    applied: list[Migration]
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "pending": [_migration_dict(item) for item in self.pending],
            "applied": [_migration_dict(item) for item in self.applied],
            "dry_run": self.dry_run,
        }


class MigrationRunner:
    def __init__(self, state_root: str | Path, migrations: list[Migration] | None = None) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.migrations = sorted(migrations if migrations is not None else default_migrations(), key=lambda item: item.version)
        self.state_path = self.state_root / "schema_state.json"
        self.lock_path = self.state_root / "schema_state.lock"

    def current_version(self) -> int:
        if not self.state_path.exists():
            return 0
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return int(data.get("version") or 0)

    def pending(self) -> list[Migration]:
        version = self.current_version()
        return [migration for migration in self.migrations if migration.version > version]

    def status(self) -> MigrationReport:
        return MigrationReport(current_version=self.current_version(), pending=self.pending(), applied=[])

    def apply_pending(self, *, dry_run: bool = False) -> MigrationReport:
        with file_lock(self.lock_path):
            current = self.current_version()
            pending = [migration for migration in self.migrations if migration.version > current]
            if dry_run:
                return MigrationReport(current_version=current, pending=pending, applied=[], dry_run=True)
            applied: list[Migration] = []
            for migration in pending:
                migration.apply(self.state_root)
                applied.append(migration)
                current = migration.version
                self._write_state(current)
            return MigrationReport(current_version=current, pending=[], applied=applied)

    def _write_state(self, version: int) -> None:
        atomic_write_text(
            self.state_path,
            json.dumps({"version": version}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )


def default_migrations() -> list[Migration]:
    return [
        Migration(version=1, name="initialize-state-root", apply=_initialize_state_root),
    ]


def _initialize_state_root(root: Path) -> None:
    (root / "schema").mkdir(parents=True, exist_ok=True)


def _migration_dict(migration: Migration) -> dict[str, Any]:
    return {"version": migration.version, "name": migration.name}
