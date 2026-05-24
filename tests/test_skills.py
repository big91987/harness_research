from pathlib import Path
import os
import subprocess
import sys

from harness.skills import SkillStore


def test_skill_store_adds_searches_and_renders_context(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)

    store.add(
        "debug-tests",
        "Use pytest -q for focused checks.",
        description="Debug failing Python tests",
    )

    results = store.search("python")

    assert len(results) == 1
    assert results[0].name == "debug-tests"
    assert results[0].description == "Debug failing Python tests"
    context = store.render_context("please debug python tests")
    assert "Available skills:" in context
    assert "debug-tests" in context
    assert "pytest -q" in context


def test_skill_store_selects_context_with_budget_metadata(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.add("debug-tests", "Use pytest -q for focused checks.", description="Debug Python tests")
    store.add("long-debug", "x" * 500, description="Debug long Python failures")

    selection = store.select_context("debug python", limit=5, max_chars=120)

    assert selection.names == ["debug-tests"]
    assert "debug-tests" in selection.context
    assert "long-debug" not in selection.context
    assert selection.char_count <= 120
    assert selection.truncated is True


def test_skill_store_sanitizes_names(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)

    path = store.add("../Bad Skill!", "body")

    assert path.name == "bad-skill.md"
    assert path.parent == tmp_path.resolve()


def test_skill_store_gets_and_deletes_skill(tmp_path: Path) -> None:
    store = SkillStore(tmp_path)
    store.add("Debug Tests", "Use pytest.", description="Debug Python tests")

    skill = store.get("debug-tests")

    assert skill.name == "debug-tests"
    assert skill.body == "Use pytest."
    assert store.delete("debug-tests")
    assert store.get("debug-tests") is None
    assert not store.delete("debug-tests")


def test_skill_store_serializes_concurrent_adds(tmp_path: Path) -> None:
    script = """
from harness.skills import SkillStore
import sys

SkillStore(sys.argv[1]).add(sys.argv[2], sys.argv[3], description=sys.argv[4])
"""

    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path),
                f"skill-{index}",
                f"body-{index}",
                f"description-{index}",
            ],
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

    skills = SkillStore(tmp_path).list()

    assert {skill.name for skill in skills} == {f"skill-{index}" for index in range(8)}
    assert {skill.body for skill in skills} == {f"body-{index}" for index in range(8)}
