"""Tests for manual and sample AI session capture commands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    parse_sessions,
    write_unattributed_session,
)
from halyard.cli import app
from halyard.hub import set_hub

runner = CliRunner()


def _session() -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 7, 10, 0, 0),
        end=datetime(2026, 5, 7, 10, 30, 0),
        tool="codex",
        model="gpt-5.5",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
    )


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
    assert session.source == "manual"


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


def test_assign_unattributed_command_uses_project_option(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    runner.invoke(app, ["record-session", "--tool", "codex"])

    result = runner.invoke(app, ["assign-unattributed", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    assert parse_sessions(tmp_path)[0].project == "acme:auth"


def test_assign_unattributed_global_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = runner.invoke(app, ["assign-unattributed"])

    assert result.exit_code == 0, result.output
    assert "No unattributed sessions" in result.output


def test_assign_unattributed_global_assigns_to_current_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    assert parse_sessions(tmp_path)[0].project == "acme:auth"
    assert (tmp_path / ".halyard" / "unattributed.log").read_text() == ""


def test_assign_unattributed_global_moves_to_hub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = tmp_path / "work"
    hub = tmp_path / "hub"
    work.mkdir()
    hub.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(hub)
    set_hub(hub)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed"], input="h\n")

    assert result.exit_code == 0, result.output
    assert parse_sessions(hub)[0].tool == "codex"
    assert (tmp_path / ".halyard" / "unattributed.log").read_text() == ""


def test_assign_unattributed_global_discards_after_confirm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed"], input="d\ny\n")

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".halyard" / "unattributed.log").read_text() == ""


def test_assign_unattributed_global_skip_keeps_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    write_unattributed_session(_session())

    result = runner.invoke(app, ["assign-unattributed"], input="s\n")

    assert result.exit_code == 0, result.output
    assert "codex" in (tmp_path / ".halyard" / "unattributed.log").read_text()


def test_check_log_reports_invalid_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    _init_project(tmp_path)
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "s bad\n")

    result = runner.invoke(app, ["check-log"])

    assert result.exit_code == 1
    assert "Line 3: expected session line" in result.output
    assert "s bad" in result.output
