"""Tests for the interactive Halyard REPL."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from halyard.repl import run_repl


def _project(tmp_path: Path) -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text("; log\n", encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Exit paths
# ---------------------------------------------------------------------------


def test_repl_exits_on_eof(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=EOFError()):
        run_repl(proj)  # must return without raising


def test_repl_exits_on_quit_command(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/quit", EOFError()]):
        run_repl(proj)


def test_repl_exits_on_q_shorthand(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/q", EOFError()]):
        run_repl(proj)


def test_repl_ctrl_c_continues_loop(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=[KeyboardInterrupt(), "/quit"]):
        run_repl(proj)


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


def test_repl_help_does_not_crash(tmp_path: Path, capsys) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/help", "/quit"]):
        run_repl(proj)


def test_repl_unknown_command_continues(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/notacommand", "/quit"]):
        run_repl(proj)  # must not raise


def test_repl_agent_switch_valid(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/agent claude", "/quit"]):
        run_repl(proj)


def test_repl_agent_switch_invalid(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/agent badprovider", "/quit"]):
        run_repl(proj)


def test_repl_period_switch_valid(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/period today", "/quit"]):
        run_repl(proj)


def test_repl_period_switch_invalid(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/period yesterday", "/quit"]):
        run_repl(proj)


def test_repl_model_set(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/model claude-opus-4-7", "/quit"]):
        run_repl(proj)


def test_repl_model_show_when_no_arg(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with patch("halyard.repl.input", side_effect=["/model", "/quit"]):
        run_repl(proj)


# ---------------------------------------------------------------------------
# Query routing
# ---------------------------------------------------------------------------


def test_repl_routes_query_to_run_log_query(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    mock_response = MagicMock()
    mock_response.answer = "You spent $1.23 this month."
    mock_response.projects = []
    mock_response.models = []

    with (
        patch("halyard.repl.input", side_effect=["how much did I spend?", "/quit"]),
        patch("halyard.repl.run_log_query", return_value=mock_response) as mock_query,
    ):
        run_repl(proj)

    mock_query.assert_called_once()
    args, kwargs = mock_query.call_args
    assert args[0] == "how much did I spend?"
    assert kwargs["project_dir"] == proj
    assert kwargs["period"] == "month"


def test_repl_period_affects_query(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    mock_response = MagicMock()
    mock_response.answer = "Today: $0.10"
    mock_response.projects = []
    mock_response.models = []

    with (
        patch("halyard.repl.input", side_effect=["/period today", "spend?", "/quit"]),
        patch("halyard.repl.run_log_query", return_value=mock_response) as mock_query,
    ):
        run_repl(proj)

    _args, kwargs = mock_query.call_args
    assert kwargs["period"] == "today"


def test_repl_agent_error_continues_loop(tmp_path: Path) -> None:
    from halyard.log_agent import LogAgentError

    proj = _project(tmp_path)
    with (
        patch("halyard.repl.input", side_effect=["bad query", "/quit"]),
        patch("halyard.repl.run_log_query", side_effect=LogAgentError("API key missing")),
    ):
        run_repl(proj)  # must not propagate the error


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_halyard_no_args_enters_repl(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from halyard.cli import app

    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text("; log\n", encoding="utf-8")

    runner = CliRunner()
    with (
        patch("halyard.ai_log.Path.cwd", return_value=tmp_path),
        patch("halyard.repl.run_repl") as mock_repl,
    ):
        result = runner.invoke(app, [])

    assert result.exit_code == 0
    mock_repl.assert_called_once()


def test_halyard_no_args_no_project_exits_nonzero(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from halyard.cli import app

    runner = CliRunner()
    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, [])

    assert result.exit_code == 1
