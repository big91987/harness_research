from pathlib import Path

from harness.storage import atomic_write_text


def test_atomic_write_text_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_atomic_write_text_creates_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.json"

    atomic_write_text(target, "ok")

    assert target.read_text(encoding="utf-8") == "ok"
