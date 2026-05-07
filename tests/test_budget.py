"""Tests for budget limits — load_budgets, check_budget, budget_status, set_budget."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import halyard.budget as budget_mod
from halyard.budget import (
    check_budget,
    load_budgets,
    set_budget,
)


def _write_budgets(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_log(project_dir: Path, lines: list[str]) -> None:
    log = project_dir / "ai-sessions.log"
    project_dir.mkdir(parents=True, exist_ok=True)
    log.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# load_budgets
# ---------------------------------------------------------------------------


def test_load_budgets_absent(tmp_path: Path) -> None:
    with patch.object(budget_mod, "_BUDGETS_FILE", tmp_path / "budgets.toml"):
        result = load_budgets()
    assert result == {}


def test_load_budgets_valid(tmp_path: Path) -> None:
    f = tmp_path / "budgets.toml"
    _write_budgets(
        f,
        '["acme:auth"]\ndaily_usd = 50.0\nmonthly_usd = 500.0\n',
    )
    with patch.object(budget_mod, "_BUDGETS_FILE", f):
        result = load_budgets()
    assert "acme:auth" in result
    assert result["acme:auth"].daily_usd == 50.0
    assert result["acme:auth"].monthly_usd == 500.0


def test_load_budgets_monthly_only(tmp_path: Path) -> None:
    f = tmp_path / "budgets.toml"
    _write_budgets(f, '["globex:reporting"]\nmonthly_usd = 200.0\n')
    with patch.object(budget_mod, "_BUDGETS_FILE", f):
        result = load_budgets()
    assert result["globex:reporting"].daily_usd is None
    assert result["globex:reporting"].monthly_usd == 200.0


def test_load_budgets_corrupted(tmp_path: Path) -> None:
    f = tmp_path / "budgets.toml"
    f.write_text("not valid toml ][[[")
    with patch.object(budget_mod, "_BUDGETS_FILE", f):
        result = load_budgets()
    assert result == {}


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 7, 14, 0, 0)

_BUDGET_TOML = '["acme:auth"]\ndaily_usd = 50.0\nmonthly_usd = 500.0\n'

_SESSION_WITHIN = (
    "s 2026-05-07T10:00:00 2026-05-07T11:00:00 claude-code claude-sonnet-4-6 "
    "100000 50000 30.0000 project=acme:auth"
)
_SESSION_OVER_DAILY = (
    "s 2026-05-07T10:00:00 2026-05-07T11:00:00 claude-code claude-sonnet-4-6 "
    "100000 50000 55.0000 project=acme:auth"
)
_SESSION_OVER_MONTHLY = (
    "s 2026-05-01T10:00:00 2026-05-01T11:00:00 claude-code claude-sonnet-4-6 "
    "100000 50000 480.0000 project=acme:auth"
)
_SESSION_CREDITS = (
    "s 2026-05-07T10:00:00 2026-05-07T11:00:00 cursor cursor-unknown "
    "0 0 0.0000 billing=credits project=acme:auth"
)
_SESSION_SEAT = (
    "s 2026-05-07T10:00:00 2026-05-07T11:00:00 cursor cursor-unknown "
    "0 0 0.0000 billing=seat project=acme:auth"
)
_SESSION_ZERO_COST = (
    "s 2026-05-07T10:00:00 2026-05-07T11:00:00 claude-code unknown-model "
    "100000 50000 0.0000 tokens_available=false project=acme:auth"
)


def test_check_budget_no_entry(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, "")
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_WITHIN])
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_absent_file(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_WITHIN])
    with patch.object(budget_mod, "_BUDGETS_FILE", tmp_path / "missing.toml"):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_within_limits(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, _BUDGET_TOML)
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_WITHIN])
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_daily_exceeded(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, _BUDGET_TOML)
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_OVER_DAILY])
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is not None
    assert "acme:auth" in result
    assert "55.00" in result
    assert "50.00" in result
    assert "over daily limit" in result


def test_check_budget_monthly_exceeded(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, _BUDGET_TOML)
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_WITHIN, _SESSION_OVER_MONTHLY])
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is not None
    assert "over monthly limit" in result


def test_check_budget_both_exceeded(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, _BUDGET_TOML)
    project_dir = tmp_path / "project"
    # 55 today (over 50 daily) + 480 earlier this month (total 535 > 500 monthly)
    _write_log(project_dir, [_SESSION_OVER_DAILY, _SESSION_OVER_MONTHLY])
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is not None
    assert "over daily limit" in result
    assert "over monthly limit" in result


def test_check_budget_excludes_credits_sessions(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, '["acme:auth"]\ndaily_usd = 10.0\n')
    project_dir = tmp_path / "project"
    # Write only credits sessions — should not trigger the limit
    _write_log(project_dir, [_SESSION_CREDITS] * 100)
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_excludes_seat_sessions(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, '["acme:auth"]\ndaily_usd = 10.0\n')
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_SEAT] * 100)
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_excludes_zero_cost_sessions(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, '["acme:auth"]\ndaily_usd = 10.0\n')
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_ZERO_COST] * 100)
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_no_log_file(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, _BUDGET_TOML)
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    # No log file written
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is None


def test_check_budget_session_proceeds_after_warning(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, _BUDGET_TOML)
    project_dir = tmp_path / "project"
    _write_log(project_dir, [_SESSION_OVER_DAILY])
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = check_budget("acme:auth", project_dir, now=_NOW)
    assert result is not None
    assert "Session will proceed" in result


# ---------------------------------------------------------------------------
# set_budget
# ---------------------------------------------------------------------------


def test_set_budget_creates_file(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = set_budget("acme:auth", daily_usd=50.0, monthly_usd=500.0)
    assert bf.exists()
    assert result.daily_usd == 50.0
    assert result.monthly_usd == 500.0


def test_set_budget_updates_existing(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, '["acme:auth"]\ndaily_usd = 50.0\nmonthly_usd = 500.0\n')
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        result = set_budget("acme:auth", daily_usd=75.0)
    assert result.daily_usd == 75.0
    assert result.monthly_usd == 500.0  # preserved


def test_set_budget_preserves_other_entries(tmp_path: Path) -> None:
    bf = tmp_path / "budgets.toml"
    _write_budgets(bf, '["globex:reporting"]\nmonthly_usd = 200.0\n')
    with patch.object(budget_mod, "_BUDGETS_FILE", bf):
        set_budget("acme:auth", monthly_usd=300.0)
        result = load_budgets()
    assert "globex:reporting" in result
    assert "acme:auth" in result
