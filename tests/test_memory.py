from pathlib import Path

from harness.memory import MarkdownMemoryStore


def test_markdown_memory_store_appends_and_searches(tmp_path: Path) -> None:
    memory = MarkdownMemoryStore(tmp_path)

    memory.add("project uses a local harness")
    memory.add("prefer TDD for kernel changes")

    results = memory.search("kernel")

    assert len(results) == 1
    assert "TDD" in results[0]
    assert "project uses" in memory.render_context()

