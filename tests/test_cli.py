from pathlib import Path

from harness.cli import build_parser


def test_cli_parser_accepts_run_options(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "hello",
            "--workspace",
            str(tmp_path),
            "--session-dir",
            str(tmp_path / "sessions"),
            "--trace",
            str(tmp_path / "trace.jsonl"),
            "--model",
            "test-model",
            "--base-url",
            "https://example.com",
        ]
    )

    assert args.command == "run"
    assert args.prompt == "hello"
    assert args.workspace == str(tmp_path)

