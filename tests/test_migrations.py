from __future__ import annotations

import json
import subprocess
import sys

from harness.migrations import Migration, MigrationRunner


def test_migration_runner_applies_pending_migrations_once(tmp_path) -> None:  # noqa: ANN001
    marker = tmp_path / "marker.txt"

    def apply(root):  # noqa: ANN001
        marker.write_text("applied", encoding="utf-8")

    runner = MigrationRunner(tmp_path, [Migration(version=1, name="create-marker", apply=apply)])

    first = runner.apply_pending()
    second = runner.apply_pending()

    assert [item.version for item in first.applied] == [1]
    assert second.applied == []
    assert runner.current_version() == 1
    assert marker.read_text(encoding="utf-8") == "applied"


def test_migration_runner_dry_run_reports_without_applying(tmp_path) -> None:  # noqa: ANN001
    marker = tmp_path / "marker.txt"
    runner = MigrationRunner(
        tmp_path,
        [Migration(version=1, name="create-marker", apply=lambda root: marker.write_text("applied"))],
    )

    report = runner.apply_pending(dry_run=True)

    assert [item.name for item in report.pending] == ["create-marker"]
    assert report.applied == []
    assert runner.current_version() == 0
    assert not marker.exists()


def test_cli_migrations_status_and_apply(tmp_path) -> None:  # noqa: ANN001
    status = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "migrations",
            "--state-root",
            str(tmp_path),
            "--status",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )
    apply = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "migrations",
            "--state-root",
            str(tmp_path),
            "--apply",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )

    assert json.loads(status.stdout)["current_version"] == 0
    payload = json.loads(apply.stdout)
    assert payload["current_version"] >= 1
    assert payload["applied"]
