from __future__ import annotations

from pathlib import Path
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
