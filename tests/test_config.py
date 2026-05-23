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
          "skill_dir": "skills",
          "task_dir": "tasks",
          "hook_config": "hooks.json",
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
          "max_iterations": 7,
          "max_model_retries": 2,
          "input_cost_per_million_tokens": 1.25,
          "output_cost_per_million_tokens": 2.5,
          "max_total_tokens": 1000,
          "max_cost_usd": 0.02
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("HARNESS_MODEL", "env-model")

    config = HarnessConfig.load(config_path)

    assert config.workspace == "ws"
    assert config.skill_dir == "skills"
    assert config.task_dir == "tasks"
    assert config.hook_config == "hooks.json"
    assert config.model == "env-model"
    assert config.permission == "workspace-write"
    assert config.allowed_tools == ["read_file", "write_file"]
    assert config.denied_tools == ["bash"]
    assert config.max_output_chars == 100
    assert config.max_file_read_bytes == 200
    assert config.default_bash_timeout_seconds == 3
    assert config.max_bash_timeout_seconds == 5
    assert config.max_iterations == 7
    assert config.max_model_retries == 2
    assert config.input_cost_per_million_tokens == 1.25
    assert config.output_cost_per_million_tokens == 2.5
    assert config.max_total_tokens == 1000
    assert config.max_cost_usd == 0.02
    assert "from-config" not in config.redacted_dict().values()


def test_config_loads_cost_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_INPUT_COST_PER_MILLION_TOKENS", "3.5")
    monkeypatch.setenv("HARNESS_OUTPUT_COST_PER_MILLION_TOKENS", "7.0")
    monkeypatch.setenv("HARNESS_MAX_TOTAL_TOKENS", "42")
    monkeypatch.setenv("HARNESS_MAX_COST_USD", "0.25")
    monkeypatch.setenv("HARNESS_SKILL_DIR", "env-skills")
    monkeypatch.setenv("HARNESS_TASK_DIR", "env-tasks")
    monkeypatch.setenv("HARNESS_HOOK_CONFIG", "env-hooks.json")
    monkeypatch.setenv("HARNESS_MAX_MODEL_RETRIES", "3")

    config = HarnessConfig.load()

    assert config.input_cost_per_million_tokens == 3.5
    assert config.output_cost_per_million_tokens == 7.0
    assert config.max_total_tokens == 42
    assert config.max_cost_usd == 0.25
    assert config.skill_dir == "env-skills"
    assert config.task_dir == "env-tasks"
    assert config.hook_config == "env-hooks.json"
    assert config.max_model_retries == 3
