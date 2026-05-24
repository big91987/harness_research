from __future__ import annotations

import contextlib
import fcntl
from pathlib import Path
from typing import Iterator
from uuid import uuid4


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        temp.write_text(text, encoding=encoding)
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink()
    return target


def locked_append_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    target = Path(path).expanduser().resolve()
    with file_lock(_lock_path_for(target)):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding=encoding) as handle:
            handle.write(text)
    return target


@contextlib.contextmanager
def file_lock(path: str | Path) -> Iterator[Path]:
    lock_path = Path(path).expanduser().resolve()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _lock_path_for(path: Path) -> Path:
    return path.with_name(f"{path.name}.lock")
