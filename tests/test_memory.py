from pathlib import Path
import os
import subprocess
import sys

from harness.memory import MarkdownMemoryStore


def test_markdown_memory_store_appends_and_searches(tmp_path: Path) -> None:
    memory = MarkdownMemoryStore(tmp_path)

    memory.add("project uses a local harness")
    memory.add("prefer TDD for kernel changes")

    results = memory.search("kernel")

    assert len(results) == 1
    assert "TDD" in results[0]
    assert "project uses" in memory.render_context()


def test_markdown_memory_store_lists_and_clears_items(tmp_path: Path) -> None:
    memory = MarkdownMemoryStore(tmp_path)
    memory.add("first fact")
    memory.add("second fact")

    assert memory.list() == ["- first fact", "- second fact"]

    memory.clear()

    assert memory.list() == []
    assert memory.render_context() == ""


def test_markdown_memory_store_serializes_concurrent_adds(tmp_path: Path) -> None:
    script = """
from harness.memory import MarkdownMemoryStore
import sys

MarkdownMemoryStore(sys.argv[1]).add(sys.argv[2])
"""

    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), f"fact-{index}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": "src"},
        )
        for index in range(8)
    ]
    for process in processes:
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stdout + stderr

    items = MarkdownMemoryStore(tmp_path).list()

    assert set(items) == {f"- fact-{index}" for index in range(8)}
