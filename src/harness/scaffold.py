from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScaffoldResult:
    root: Path
    config_path: Path
    mock_responses_path: Path
    golden_path: Path


def scaffold_project(root: str | Path, *, overwrite: bool = False) -> ScaffoldResult:
    root_path = Path(root).expanduser().resolve()
    samples = root_path / "samples"
    workspace = root_path / "workspace"
    sessions = root_path / "sessions"
    memory = root_path / "memory"
    artifacts = root_path / "artifacts"
    root_path.mkdir(parents=True, exist_ok=True)
    for directory in (samples, workspace, sessions, memory, artifacts):
        directory.mkdir(parents=True, exist_ok=True)

    config_path = root_path / "harness.json"
    responses_path = samples / "mock_responses.json"
    golden_path = samples / "golden.json"

    _write_json(
        config_path,
        {
            "workspace": str(workspace),
            "session_dir": str(sessions),
            "trace": str(root_path / "trace.jsonl"),
            "audit": str(root_path / "audit.jsonl"),
            "artifact_dir": str(artifacts),
            "memory_dir": str(memory),
            "permission": "workspace-write",
            "denied_tools": ["bash"],
            "max_output_chars": 20000,
            "max_file_read_bytes": 1000000,
            "default_bash_timeout_seconds": 30,
            "max_bash_timeout_seconds": 120,
            "model": "gpt-4.1-mini",
            "max_iterations": 20,
        },
        overwrite=overwrite,
    )
    _write_json(
        responses_path,
        [
            {
                "content": "writing sample",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "write_file",
                        "arguments": {
                            "path": "sample.txt",
                            "content": "hello from harness",
                        },
                    }
                ],
            },
            {"content": "created sample.txt"},
        ],
        overwrite=overwrite,
    )
    _write_json(
        golden_path,
        {
            "cases": [
                {
                    "name": "sample-write",
                    "trace": str(root_path / "trace.jsonl"),
                    "expect": {
                        "stop_reason": "final_answer",
                        "required_tools": ["write_file"],
                        "max_tool_errors": 0,
                        "final_text_contains": "created sample.txt",
                    },
                }
            ]
        },
        overwrite=overwrite,
    )
    return ScaffoldResult(root_path, config_path, responses_path, golden_path)


def _write_json(path: Path, data: object, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
