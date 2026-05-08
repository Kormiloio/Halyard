"""Tests for v2.8 calendar block export and seed-demo command."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from halyard.ai_log import AiSession
from halyard.schedule import _session_uid, build_calendar, session_to_vevent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(**kw: Any) -> AiSession:
    defaults: dict[str, Any] = {
        "start": datetime(2026, 5, 7, 10, 0),
        "end": datetime(2026, 5, 7, 10, 30),
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "input_tokens": 18000,
        "output_tokens": 3200,
        "cost_usd": 0.45,
    }
    defaults.update(kw)
    return AiSession(**defaults)


# ---------------------------------------------------------------------------
# UID stability
# ---------------------------------------------------------------------------


def test_uid_is_stable() -> None:
    s = _session()
    assert _session_uid(s) == _session_uid(s)


def test_uid_differs_across_sessions() -> None:
    s1 = _session(cost_usd=0.45)
    s2 = _session(cost_usd=0.99)
    assert _session_uid(s1) != _session_uid(s2)


def test_uid_ends_with_halyard_suffix() -> None:
    s = _session()
    assert _session_uid(s).endswith("@halyard")


# ---------------------------------------------------------------------------
# VEVENT structure
# ---------------------------------------------------------------------------


def test_vevent_contains_required_fields() -> None:
    s = _session(project="acme:auth")
    vevent = session_to_vevent(s)
    assert "BEGIN:VEVENT" in vevent
    assert "END:VEVENT" in vevent
    assert "DTSTART:20260507T100000" in vevent
    assert "DTEND:20260507T103000" in vevent
    assert "SUMMARY:claude-code — acme:auth" in vevent
    assert "UID:" in vevent


def test_vevent_unattributed_project() -> None:
    s = _session()  # no project
    vevent = session_to_vevent(s)
    assert "SUMMARY:claude-code — unattributed" in vevent


def test_vevent_description_includes_model_and_cost() -> None:
    s = _session(project="acme:auth")
    vevent = session_to_vevent(s)
    assert "claude-sonnet-4-6" in vevent
    assert "$0.4500" in vevent


def test_vevent_includes_tool_calls_when_present() -> None:
    s = _session(tool_calls=32, tool_errors=3)
    vevent = session_to_vevent(s)
    assert "Tool calls: 32" in vevent


def test_vevent_includes_code_delta_when_present() -> None:
    s = _session(code_added=88, code_removed=12)
    vevent = session_to_vevent(s)
    assert "Code delta: +88/-12" in vevent


def test_vevent_omits_optional_fields_when_absent() -> None:
    s = _session()
    vevent = session_to_vevent(s)
    assert "Tool calls" not in vevent
    assert "Code delta" not in vevent


# ---------------------------------------------------------------------------
# Full calendar
# ---------------------------------------------------------------------------


def test_build_calendar_wraps_in_vcalendar() -> None:
    sessions = [_session(project="acme:auth"), _session(project="acme:api")]
    cal = build_calendar(sessions)
    assert cal.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in cal
    assert cal.count("BEGIN:VEVENT") == 2


def test_build_calendar_empty_sessions() -> None:
    cal = build_calendar([])
    assert "BEGIN:VCALENDAR" in cal
    assert "BEGIN:VEVENT" not in cal


def test_build_calendar_uses_crlf() -> None:
    cal = build_calendar([_session()])
    assert "\r\n" in cal


# ---------------------------------------------------------------------------
# CLI: schedule command
# ---------------------------------------------------------------------------


def test_schedule_cli_writes_file(tmp_path: Any) -> None:
    from halyard.cli import app

    sessions = [_session(project="acme:auth")]
    runner = CliRunner()
    out_path = str(tmp_path / "out.ics")

    with (
        patch("halyard.ai_log.find_project_dir", return_value=tmp_path),
        patch("halyard.ai_log.parse_sessions", return_value=sessions),
    ):
        result = runner.invoke(app, ["schedule", "--period", "all", "--output", out_path])

    assert result.exit_code == 0
    assert "Exported" in result.output
    ics_content = (tmp_path / "out.ics").read_text()
    assert "BEGIN:VCALENDAR" in ics_content


def test_schedule_cli_stdout(tmp_path: Any) -> None:
    from halyard.cli import app

    sessions = [_session(project="acme:auth")]
    runner = CliRunner()

    with (
        patch("halyard.ai_log.find_project_dir", return_value=tmp_path),
        patch("halyard.ai_log.parse_sessions", return_value=sessions),
    ):
        result = runner.invoke(app, ["schedule", "--period", "all", "--stdout"])

    assert result.exit_code == 0
    assert "BEGIN:VCALENDAR" in result.output


def test_schedule_cli_exits_1_no_project() -> None:
    from halyard.cli import app

    runner = CliRunner()
    with (
        patch("halyard.ai_log.find_project_dir", return_value=None),
        patch("halyard.hub.find_hub", return_value=None),
    ):
        result = runner.invoke(app, ["schedule"])

    assert result.exit_code == 1
    assert "No Halyard project found" in result.output


# ---------------------------------------------------------------------------
# CLI: seed-demo command
# ---------------------------------------------------------------------------


def test_seed_demo_writes_sessions(tmp_path: Any) -> None:
    from halyard.ai_log import AI_LOG_FILENAME, parse_sessions
    from halyard.cli import app

    (tmp_path / "halyard.toml").write_text("[project]\n")
    (tmp_path / AI_LOG_FILENAME).write_text(
        "; Halyard AI session log\n"
        "; s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>\n"
    )

    runner = CliRunner()
    with patch("halyard.ai_log.find_project_dir", return_value=tmp_path):
        result = runner.invoke(app, ["seed-demo", "--yes"])

    assert result.exit_code == 0
    assert "Seeded" in result.output
    sessions = parse_sessions(tmp_path)
    assert len(sessions) >= 25


def test_seed_demo_warns_without_yes(tmp_path: Any) -> None:
    from halyard.ai_log import AI_LOG_FILENAME
    from halyard.cli import app

    (tmp_path / "halyard.toml").write_text("[project]\n")
    # Pre-populate with one fake session line
    (tmp_path / AI_LOG_FILENAME).write_text(
        "; header\n"
        "s 2026-05-01T10:00:00 2026-05-01T10:30:00 claude-code claude-sonnet 1000 200 0.1000\n"
    )

    runner = CliRunner()
    with patch("halyard.ai_log.find_project_dir", return_value=tmp_path):
        result = runner.invoke(app, ["seed-demo"])

    assert result.exit_code == 1
    assert "--yes" in result.output
