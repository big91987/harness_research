from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from harness.config import HarnessConfig
from harness.secrets import SecretStore, resolve_api_key


def test_secret_store_sets_gets_lists_and_deletes_values(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    store = SecretStore(path)

    store.set("deepseek", "sk-test")

    assert store.get("deepseek") == "sk-test"
    assert store.list_names() == ["deepseek"]
    assert "sk-test" not in json.dumps(store.redacted_dict())
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.delete("deepseek") is True
    assert store.get("deepseek") is None


def test_resolve_api_key_prefers_explicit_value_then_secret(tmp_path: Path) -> None:
    store = SecretStore(tmp_path / "secrets.json")
    store.set("model-key", "from-secret")

    assert resolve_api_key(HarnessConfig(api_key="plain", api_key_secret="model-key"), store) == "plain"
    assert resolve_api_key(HarnessConfig(api_key_secret="model-key"), store) == "from-secret"
    assert resolve_api_key(HarnessConfig(api_key_secret="missing"), store) is None


def test_cli_secrets_manage_local_secret_store(tmp_path: Path) -> None:
    path = tmp_path / "secrets.json"
    set_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "secrets",
            "--secret-store",
            str(path),
            "--set",
            "deepseek",
            "--value",
            "sk-test",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )
    list_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "secrets",
            "--secret-store",
            str(path),
            "--list",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )
    get_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "secrets",
            "--secret-store",
            str(path),
            "--get",
            "deepseek",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )

    assert "stored: deepseek" in set_result.stdout
    assert json.loads(list_result.stdout) == {"deepseek": "***"}
    assert get_result.stdout == "sk-test\n"
