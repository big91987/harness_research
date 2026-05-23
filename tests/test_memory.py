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


def test_markdown_memory_store_lists_and_clears_items(tmp_path: Path) -> None:
    memory = MarkdownMemoryStore(tmp_path)
    memory.add("first fact")
    memory.add("second fact")

    assert memory.list() == ["- first fact", "- second fact"]

    memory.clear()

    assert memory.list() == []
    assert memory.render_context() == ""
