from pathlib import Path

from harness.config import HarnessConfig


def test_config_loads_json_and_overrides_env(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "harness.json"
    config_path.write_text(
        """
        {
          "workspace": "ws",
          "session_dir": "sessions",
          "trace": "trace.jsonl",
          "memory_dir": "memory",
          "base_url": "https://config.example.com",
          "api_key": "from-config",
          "model": "config-model",
          "permission": "workspace-write",
          "allowed_tools": ["read_file", "write_file"],
          "denied_tools": ["bash"],
          "max_output_chars": 100,
          "max_file_read_bytes": 200,
          "default_bash_timeout_seconds": 3,
          "max_bash_timeout_seconds": 5,
          "max_iterations": 7
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_MODEL", "env-model")

    config = HarnessConfig.load(config_path)

    assert config.workspace == "ws"
    assert config.model == "env-model"
    assert config.permission == "workspace-write"
    assert config.allowed_tools == ["read_file", "write_file"]
    assert config.denied_tools == ["bash"]
    assert config.max_output_chars == 100
    assert config.max_file_read_bytes == 200
    assert config.default_bash_timeout_seconds == 3
    assert config.max_bash_timeout_seconds == 5
    assert config.max_iterations == 7
    assert "from-config" not in config.redacted_dict().values()
