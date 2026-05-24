from pathlib import Path
import os
import subprocess
import sys

from harness.memory import MarkdownMemoryStore, SessionMemoryExtractor
from harness.model import FakeModelClient
from harness.schema import Message, ModelResponse
from harness.session import Session


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


def test_session_memory_extractor_adds_model_items(tmp_path: Path) -> None:
    memory = MarkdownMemoryStore(tmp_path / "memory")
    session = Session.new(workspace=str(tmp_path / "ws"))
    session.messages.append(Message.user("Use TDD and keep changes small."))
    session.messages.append(Message.assistant("Noted."))
    model = FakeModelClient([ModelResponse(content='["Prefer TDD.", "Keep changes small."]')])

    added = SessionMemoryExtractor(model=model, memory=memory).extract(session)

    assert added == ["Prefer TDD.", "Keep changes small."]
    assert memory.list() == ["- Prefer TDD.", "- Keep changes small."]
    assert "Use TDD" in model.calls[0][-1].content


def test_session_memory_extractor_ignores_empty_and_duplicate_items(tmp_path: Path) -> None:
    memory = MarkdownMemoryStore(tmp_path / "memory")
    memory.add("Prefer TDD.")
    session = Session.new(workspace=str(tmp_path / "ws"))
    session.messages.append(Message.user("Prefer TDD."))
    model = FakeModelClient([ModelResponse(content='["", "Prefer TDD.", "Use real model validation."]')])

    added = SessionMemoryExtractor(model=model, memory=memory).extract(session)

    assert added == ["Use real model validation."]
    assert memory.list() == ["- Prefer TDD.", "- Use real model validation."]
