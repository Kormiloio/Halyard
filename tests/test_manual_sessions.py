"""Tests for manual and sample AI session capture commands."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, parse_sessions
from halyard.cli import app

runner = CliRunner()


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


def test_record_session_appends_manual_session(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(
        app,
        [
            "record-session",
            "--project",
            "acme:auth",
            "--tool",
            "codex",
            "--model",
            "claude-sonnet-4-6",
            "--input-tokens",
            "1000",
            "--output-tokens",
            "500",
        ],
    )

    assert result.exit_code == 0, result.output
    session = parse_sessions(tmp_path)[0]
    assert session.tool == "codex"
    assert session.project == "acme:auth"
    assert session.input_tokens == 1000
    assert session.output_tokens == 500
    assert session.source == "codex"


def test_sample_session_appends_realistic_session(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    _init_project(tmp_path)

    result = runner.invoke(app, ["sample-session", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    session = parse_sessions(tmp_path)[0]
    assert session.tool == "claude-code"
    assert session.model == "claude-sonnet-4-6"
    assert session.project == "acme:auth"
    assert session.input_tokens > 0
    assert session.cost_usd > 0
