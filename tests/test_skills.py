from pathlib import Path

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
