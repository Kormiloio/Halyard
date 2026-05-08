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


def test_render_dashboard_shows_human_time(tmp_path: Path) -> None:
    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text(
        "i 2026-05-07 09:00:00 acme:auth\no 2026-05-07 10:00:00\n"
    )

    html = render_dashboard(tmp_path)

    assert "Human Time" in html
    assert "Timeclock" in html
    assert "acme:auth" in html


def test_render_dashboard_health_column_with_tool_telemetry(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="gemini-cli",
            model="gemini-2.0-flash",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.0012,
            project="acme:auth",
            tool_calls=20,
            tool_errors=3,
            code_added=45,
            code_removed=12,
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Health" in html
    assert "20c" in html
    assert "3e" in html
    assert "+45/-12" in html


def test_render_dashboard_health_column_no_telemetry(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 8, 10, 0),
            end=datetime(2026, 5, 8, 10, 30),
            tool="claude-code",
            model="claude-sonnet-4-6",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.005,
            project="acme:auth",
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Health" in html
    assert "—" in html


def test_render_dashboard_marks_unattributed_sessions(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(
        tmp_path,
        AiSession(
            start=datetime(2026, 5, 7, 10, 0),
            end=datetime(2026, 5, 7, 10, 30),
            tool="codex",
            model="codex-local",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0,
        ),
    )

    html = render_dashboard(tmp_path)

    assert "Needs Attention" in html
    assert "Unattributed Sessions" in html
    assert "codex-local" in html
