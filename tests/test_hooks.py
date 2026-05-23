import json
import sys
from pathlib import Path

from harness.hooks import HookRunner


def test_hook_runner_executes_matching_command_with_event_stdin(tmp_path: Path) -> None:
    script = tmp_path / "hook.py"
    out = tmp_path / "hook-output.json"
    script.write_text(
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(out)!r}).write_text(json.dumps(json.load(sys.stdin)), encoding='utf-8')\n"
        "print('hook-ok')\n",
        encoding="utf-8",
    )
    config = tmp_path / "hooks.json"
    config.write_text(
        json.dumps(
            {
                "hooks": [
                    {
                        "event": "turn_end",
                        "command": [sys.executable, str(script)],
                        "timeout_seconds": 5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    runner = HookRunner.from_config(config, cwd=tmp_path)
    results = runner.run("turn_end", {"session_id": "s1", "stop_reason": "final_answer"})

    assert len(results) == 1
    assert results[0].returncode == 0
    assert "hook-ok" in results[0].stdout
    assert json.loads(out.read_text(encoding="utf-8"))["session_id"] == "s1"


def test_hook_runner_ignores_unmatched_events(tmp_path: Path) -> None:
    config = tmp_path / "hooks.json"
    config.write_text(
        json.dumps({"hooks": [{"event": "turn_start", "command": [sys.executable, "-c", "print('x')"]}]}),
        encoding="utf-8",
    )

    runner = HookRunner.from_config(config, cwd=tmp_path)

    assert runner.run("turn_end", {}) == []
