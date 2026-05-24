from __future__ import annotations

import json
import subprocess
import sys
import time

from harness.cache import FileCache


def test_file_cache_sets_gets_expires_and_deletes_values(tmp_path) -> None:  # noqa: ANN001
    cache = FileCache(tmp_path / "cache")

    cache.set("model", {"prompt": "hi"}, {"answer": "hello"}, ttl_seconds=1)

    assert cache.get("model", {"prompt": "hi"}) == {"answer": "hello"}
    assert cache.get("model", {"prompt": "other"}) is None
    assert len(cache.list_entries(namespace="model")) == 1
    time.sleep(1.1)
    assert cache.get("model", {"prompt": "hi"}) is None
    assert cache.delete("model", {"prompt": "hi"}) is True


def test_file_cache_clear_namespace(tmp_path) -> None:  # noqa: ANN001
    cache = FileCache(tmp_path / "cache")
    cache.set("model", {"a": 1}, "a")
    cache.set("tool", {"a": 1}, "b")

    assert cache.clear(namespace="model") == 1
    assert cache.get("model", {"a": 1}) is None
    assert cache.get("tool", {"a": 1}) == "b"


def test_cli_cache_can_set_get_list_and_clear(tmp_path) -> None:  # noqa: ANN001
    cache_dir = tmp_path / "cache"
    key = json.dumps({"prompt": "hi"})
    value = json.dumps({"answer": "hello"})

    set_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "cache",
            "--cache-dir",
            str(cache_dir),
            "--namespace",
            "model",
            "--key-json",
            key,
            "--set-json",
            value,
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
            "cache",
            "--cache-dir",
            str(cache_dir),
            "--namespace",
            "model",
            "--key-json",
            key,
            "--get",
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
            "cache",
            "--cache-dir",
            str(cache_dir),
            "--namespace",
            "model",
            "--list",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
        env={"PYTHONPATH": "src"},
    )

    assert "stored:" in set_result.stdout
    assert json.loads(get_result.stdout) == {"answer": "hello"}
    assert json.loads(list_result.stdout)[0]["namespace"] == "model"
