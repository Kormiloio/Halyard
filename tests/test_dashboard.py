"""Tests for the local Glass Cockpit dashboard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app
from halyard.dashboard import render_dashboard

runner = CliRunner()


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / "time.timeclock").write_text("; time\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


def test_dashboard_command_registered() -> None:
    result = runner.invoke(app, ["dashboard", "--help"])

    assert result.exit_code == 0
    assert "Glass Cockpit" in result.output


def test_render_dashboard_shows_cockpit_and_session(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.01,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Halyard Glass Cockpit" in html
    assert "Recent AI Sessions" in html
    assert "acme:auth" in html
    assert "claude-sonnet-4-6" in html
