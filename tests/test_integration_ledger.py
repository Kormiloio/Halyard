"""Integration tests: collector → log file → ledger → CLI report.

These tests exercise the full data path rather than individual units:
  append_session() writes to disk
  parse_sessions() reads it back
  build_ledger() allocates cost
  `halyard report --ledger` renders the result
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session
from halyard.cli import app

runner = CliRunner()

_NOW = datetime(2026, 5, 7, 10, 0, 0)


def _session(
    *,
    project: str | None = None,
    tool: str = "claude-code",
    model: str = "claude-sonnet-4-6",
    cost: float = 1.00,
    input_tokens: int = 10_000,
    output_tokens: int = 2_000,
    minutes: int = 60,
    billing: str = "api",
    credits: float | None = None,
) -> AiSession:
    return AiSession(
        start=_NOW,
        end=_NOW + timedelta(minutes=minutes),
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        project=project,
        billing=billing,
        credits=credits,
    )


def _init_project(tmp_path: Path, plans_toml: str | None = None) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)
    if plans_toml is not None:
        (tmp_path / "ai-plans.toml").write_text(plans_toml)


# ---------------------------------------------------------------------------
# Round-trip: append → parse → report
# ---------------------------------------------------------------------------


def test_appended_sessions_appear_in_report(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(tmp_path, _session(project="acme:auth", cost=3.50))
    append_session(tmp_path, _session(project="acme:auth", cost=1.50))

    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report"])

    assert result.exit_code == 0
    assert "$5.00" in result.output
    assert "acme:auth" in result.output


def test_note_with_newline_does_not_corrupt_log(tmp_path: Path) -> None:
    _init_project(tmp_path)
    session = _session(project="acme:auth", cost=1.00)
    session = AiSession(**{**session.__dict__, "note": "line one\nline two"})
    append_session(tmp_path, session)

    log_text = (tmp_path / AI_LOG_FILENAME).read_text()
    data_lines = [ln for ln in log_text.splitlines() if ln.startswith("s ")]
    assert len(data_lines) == 1, "newline in note must not produce extra log lines"
    # Newline is percent-encoded (%0A) and the literal raw newline is gone.
    assert "\n" not in data_lines[0]
    assert "%0A" in data_lines[0]


# ---------------------------------------------------------------------------
# Ledger path: append → plans file → report --ledger
# ---------------------------------------------------------------------------


def test_report_ledger_direct_api_shows_captured_cost(tmp_path: Path) -> None:
    plans = (
        "[[plan]]\nslug = 'direct'\ntool = 'claude-code'\nbilling = 'api'\nallocation = 'direct'\n"
    )
    _init_project(tmp_path, plans)
    append_session(tmp_path, _session(project="acme:auth", cost=4.00, billing="api"))

    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report", "--ledger"])

    assert result.exit_code == 0, result.output
    assert "acme:auth" in result.output
    assert "$4.00" in result.output


def test_report_ledger_seat_plan_allocates_full_monthly_cost(tmp_path: Path) -> None:
    plans = (
        "[[plan]]\n"
        "slug = 'seat'\n"
        "tool = 'claude-code'\n"
        "billing = 'seat'\n"
        "monthly_usd = 100.0\n"
        "allocation = 'active_minutes'\n"
    )
    _init_project(tmp_path, plans)
    # Two projects with 30 min each → equal 50/50 split of $100
    s1 = AiSession(
        start=_NOW,
        end=_NOW + timedelta(minutes=30),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.0,
        project="acme:auth",
        billing="seat",
    )
    s2 = AiSession(
        start=_NOW,
        end=_NOW + timedelta(minutes=30),
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=0.0,
        project="globex:dash",
        billing="seat",
    )
    append_session(tmp_path, s1)
    append_session(tmp_path, s2)

    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report", "--ledger"])

    assert result.exit_code == 0, result.output
    assert "acme:auth" in result.output
    assert "globex:dash" in result.output
    assert "$50.00" in result.output


def test_report_ledger_no_plans_file_shows_hint(tmp_path: Path) -> None:
    _init_project(tmp_path)  # no ai-plans.toml
    append_session(tmp_path, _session(project="acme:auth", cost=2.00))

    with patch("halyard.ai_log.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["report", "--ledger"])

    assert result.exit_code == 0, result.output
    assert "ai-plans.toml" in result.output
