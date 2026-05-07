"""Tests for `halyard report` (task v1 3.1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app

runner = CliRunner()

_THIS_MONTH = datetime.now()
_LAST_MONTH = datetime(_THIS_MONTH.year, _THIS_MONTH.month - 1 if _THIS_MONTH.month > 1 else 12, 15)


def _s(
    *,
    project: str | None = None,
    model: str = "claude-sonnet-4-6",
    cost: float = 1.00,
    month: datetime = _THIS_MONTH,
) -> AiSession:
    return AiSession(
        start=month.replace(day=1, hour=10),
        end=month.replace(day=1, hour=11),
        tool="claude-code",
        model=model,
        input_tokens=10000,
        output_tokens=2000,
        cost_usd=cost,
        project=project,
    )


def _init(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


def test_report_no_sessions_this_month(tmp_path: Path) -> None:
    _init(tmp_path)
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "No AI sessions" in result.output


def test_report_shows_session_count_and_cost(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(cost=2.50))
    append_session(tmp_path, _s(cost=1.50))
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "2" in result.output  # session count
    assert "$4.00" in result.output  # total cost


def test_report_groups_by_project(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(project="acme:auth", cost=3.00))
    append_session(tmp_path, _s(project="globex:reports", cost=1.00))
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])
    assert "acme:auth" in result.output
    assert "globex:reports" in result.output


def test_report_groups_by_model(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(model="claude-opus-4-7", cost=5.00))
    append_session(tmp_path, _s(model="claude-sonnet-4-6", cost=1.00))
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])
    assert "claude-opus-4-7" in result.output
    assert "claude-sonnet-4-6" in result.output


def test_report_filters_to_current_month(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(cost=5.00, month=_THIS_MONTH))
    append_session(tmp_path, _s(cost=99.00, month=_LAST_MONTH))
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])
    assert "$5.00" in result.output
    assert "$99.00" not in result.output


def test_report_all_flag_includes_all_sessions(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(cost=5.00, month=_THIS_MONTH))
    append_session(tmp_path, _s(cost=99.00, month=_LAST_MONTH))
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report", "--all"])
    assert "$104.00" in result.output


def test_report_no_halyard_project_exits_nonzero(tmp_path: Path) -> None:
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])
    assert result.exit_code == 1


def test_report_project_filter_filters_model_breakdown(tmp_path: Path) -> None:
    _init(tmp_path)
    append_session(tmp_path, _s(project="acme:auth", model="claude-sonnet-4-6", cost=1.00))
    append_session(tmp_path, _s(project="globex:reports", model="claude-opus-4-7", cost=9.00))

    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report", "--project", "acme:auth"])

    assert result.exit_code == 0, result.output
    assert "$1.00" in result.output
    assert "claude-sonnet-4-6" in result.output
    assert "claude-opus-4-7" not in result.output
    assert "$9.00" not in result.output
