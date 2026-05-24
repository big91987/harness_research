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
          "run_dir": "runs",
          "hook_config": "hooks.json",
          "base_url": "https://config.example.com",
          "api_key": "from-config",
          "model": "config-model",
          "model_timeout_seconds": 9,
          "temperature": 0.2,
          "top_p": 0.9,
          "max_tokens": 512,
          "permission": "workspace-write",
          "tool_profile": "coding",
          "allowed_tools": ["read_file", "write_file"],
          "denied_tools": ["bash"],
          "max_output_chars": 100,
          "max_file_read_bytes": 200,
          "default_bash_timeout_seconds": 3,
          "max_bash_timeout_seconds": 5,
          "sandbox_runner": "python3 /tmp/runner.py",
          "fail_fast_on_tool_error": true,
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
    monkeypatch.setenv("HARNESS_MODEL_TIMEOUT_SECONDS", "11")
    monkeypatch.setenv("HARNESS_TEMPERATURE", "0.3")

    config = HarnessConfig.load(config_path)

    assert config.workspace == "ws"
    assert config.skill_dir == "skills"
    assert config.task_dir == "tasks"
    assert config.run_dir == "runs"
    assert config.hook_config == "hooks.json"
    assert config.model == "env-model"
    assert config.model_timeout_seconds == 11
    assert config.temperature == 0.3
    assert config.top_p == 0.9
    assert config.max_tokens == 512
    assert config.permission == "workspace-write"
    assert config.tool_profile == "coding"
    assert config.allowed_tools == ["read_file", "write_file"]
    assert config.denied_tools == ["bash"]
    assert config.max_output_chars == 100
    assert config.max_file_read_bytes == 200
    assert config.default_bash_timeout_seconds == 3
    assert config.max_bash_timeout_seconds == 5
    assert config.sandbox_runner == "python3 /tmp/runner.py"
    assert config.fail_fast_on_tool_error is True
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
    monkeypatch.setenv("HARNESS_RUN_DIR", "env-runs")
    monkeypatch.setenv("HARNESS_HOOK_CONFIG", "env-hooks.json")
    monkeypatch.setenv("HARNESS_MAX_MODEL_RETRIES", "3")
    monkeypatch.setenv("HARNESS_MODEL_TIMEOUT_SECONDS", "17")
    monkeypatch.setenv("HARNESS_TOP_P", "0.75")
    monkeypatch.setenv("HARNESS_MAX_TOKENS", "2048")
    monkeypatch.setenv("HARNESS_SANDBOX_RUNNER", "python3 /tmp/env-runner.py")
    monkeypatch.setenv("HARNESS_TOOL_PROFILE", "safe")
    monkeypatch.setenv("HARNESS_FAIL_FAST_ON_TOOL_ERROR", "true")

    config = HarnessConfig.load()

    assert config.input_cost_per_million_tokens == 3.5
    assert config.output_cost_per_million_tokens == 7.0
    assert config.max_total_tokens == 42
    assert config.max_cost_usd == 0.25
    assert config.skill_dir == "env-skills"
    assert config.task_dir == "env-tasks"
    assert config.run_dir == "env-runs"
    assert config.hook_config == "env-hooks.json"
    assert config.max_model_retries == 3
    assert config.model_timeout_seconds == 17
    assert config.top_p == 0.75
    assert config.max_tokens == 2048
    assert config.sandbox_runner == "python3 /tmp/env-runner.py"
    assert config.tool_profile == "safe"
    assert config.fail_fast_on_tool_error is True


def test_config_validate_reports_errors_and_warnings() -> None:
    config = HarnessConfig(
        permission="root",
        tool_profile="unknown",
        base_url="https://api.example.com",
        api_key=None,
        allowed_tools=["read_file", "bash"],
        denied_tools=["bash"],
        max_iterations=0,
        model_timeout_seconds=0,
        max_model_retries=-1,
        temperature=-0.1,
        top_p=-0.1,
        max_tokens=0,
        default_bash_timeout_seconds=10,
        max_bash_timeout_seconds=5,
        max_cost_usd=-0.01,
    )

    issues = config.validate()

    errors = {issue.key for issue in issues if issue.level == "error"}
    warnings = {issue.key for issue in issues if issue.level == "warn"}
    assert "permission" in errors
    assert "tool_profile" in errors
    assert "max_iterations" in errors
    assert "model_timeout_seconds" in errors
    assert "max_model_retries" in errors
    assert "temperature" in errors
    assert "top_p" in errors
    assert "max_tokens" in errors
    assert "max_bash_timeout_seconds" in errors
    assert "max_cost_usd" in errors
    assert "tools" in errors
    assert "model_endpoint" in warnings


def test_config_validate_accepts_minimal_default_config() -> None:
    issues = HarnessConfig().validate()

    assert [issue for issue in issues if issue.level == "error"] == []
