"""Tests for v2.7 AI Work Health signal detectors and CLI command."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AiSession
from halyard.work_health import (
    WorkHealthReport,
    build_health_report,
    detect_high_error_rate,
    detect_high_spend_low_delta,
    detect_repeated_attempts,
    detect_unattributed_high_cost,
    detect_wall_vs_active,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(**kw: Any) -> AiSession:
    defaults: dict[str, Any] = {
        "start": datetime(2026, 5, 1, 10, 0),
        "end": datetime(2026, 5, 1, 10, 30),
        "tool": "claude-code",
        "model": "claude-sonnet",
        "input_tokens": 1000,
        "output_tokens": 200,
        "cost_usd": 0.10,
    }
    defaults.update(kw)
    return AiSession(**defaults)


# ---------------------------------------------------------------------------
# High error rate
# ---------------------------------------------------------------------------


def test_high_error_rate_fires_above_threshold() -> None:
    s = _session(tool_calls=10, tool_errors=4)  # 40% > 25%
    sig = detect_high_error_rate([s])
    assert sig.available is True
    assert s in sig.sessions


def test_high_error_rate_ignores_small_sessions() -> None:
    s = _session(tool_calls=4, tool_errors=2)  # < 5 calls, excluded
    sig = detect_high_error_rate([s])
    assert sig.available is True
    assert sig.sessions == []


def test_high_error_rate_no_data_when_no_tool_calls() -> None:
    s = _session()  # tool_calls is None
    sig = detect_high_error_rate([s])
    assert sig.available is False
    assert sig.sessions == []


def test_high_error_rate_below_threshold_not_flagged() -> None:
    s = _session(tool_calls=10, tool_errors=2)  # 20% ≤ 25%
    sig = detect_high_error_rate([s])
    assert sig.available is True
    assert sig.sessions == []


# ---------------------------------------------------------------------------
# Wall vs active time
# ---------------------------------------------------------------------------


def test_wall_vs_active_fires_below_ratio() -> None:
    s = _session(wall_seconds=100, agent_active_seconds=20)  # 20% < 30%
    sig = detect_wall_vs_active([s])
    assert sig.available is True
    assert s in sig.sessions


def test_wall_vs_active_no_flag_above_ratio() -> None:
    s = _session(wall_seconds=100, agent_active_seconds=50)  # 50% ≥ 30%
    sig = detect_wall_vs_active([s])
    assert sig.available is True
    assert sig.sessions == []


def test_wall_vs_active_no_data_when_fields_absent() -> None:
    s = _session()
    sig = detect_wall_vs_active([s])
    assert sig.available is False
    assert sig.sessions == []


# ---------------------------------------------------------------------------
# High spend, low code delta
# ---------------------------------------------------------------------------


def test_high_spend_low_delta_fires() -> None:
    # $1.00 cost, 2 lines total → 2 lines/dollar < 5.0 threshold
    s = _session(cost_usd=1.00, code_added=2, code_removed=0)
    sig = detect_high_spend_low_delta([s])
    assert sig.available is True
    assert s in sig.sessions


def test_high_spend_low_delta_no_flag_when_delta_sufficient() -> None:
    # $1.00 cost, 10 lines total → 10 lines/dollar ≥ 5.0
    s = _session(cost_usd=1.00, code_added=8, code_removed=2)
    sig = detect_high_spend_low_delta([s])
    assert sig.available is True
    assert sig.sessions == []


def test_high_spend_low_delta_no_flag_when_cost_below_threshold() -> None:
    # $0.30 < $0.50 threshold, not evaluated
    s = _session(cost_usd=0.30, code_added=1, code_removed=0)
    sig = detect_high_spend_low_delta([s])
    assert sig.available is True
    assert sig.sessions == []


def test_high_spend_low_delta_no_data_when_code_absent() -> None:
    s = _session(cost_usd=1.00)  # code_added is None
    sig = detect_high_spend_low_delta([s])
    assert sig.available is False
    assert sig.sessions == []


# ---------------------------------------------------------------------------
# Repeated attempts
# ---------------------------------------------------------------------------


def test_repeated_attempts_fires_at_threshold() -> None:
    day = datetime(2026, 5, 1, 10, 0)
    sessions = [
        _session(start=day, project="acme:auth"),
        _session(start=day, project="acme:auth"),
        _session(start=day, project="acme:auth"),
    ]
    sig = detect_repeated_attempts(sessions)
    assert sig.available is True
    assert len(sig.sessions) == 3


def test_repeated_attempts_no_flag_below_threshold() -> None:
    day = datetime(2026, 5, 1, 10, 0)
    sessions = [
        _session(start=day, project="acme:auth"),
        _session(start=day, project="acme:auth"),
    ]
    sig = detect_repeated_attempts(sessions)
    assert sig.sessions == []


def test_repeated_attempts_no_flag_without_project() -> None:
    # Sessions without project should not be grouped into flags
    day = datetime(2026, 5, 1, 10, 0)
    sessions = [_session(start=day), _session(start=day), _session(start=day)]
    sig = detect_repeated_attempts(sessions)
    assert sig.sessions == []


# ---------------------------------------------------------------------------
# Unattributed high-cost
# ---------------------------------------------------------------------------


def test_unattributed_high_cost_fires_above_p75() -> None:
    # 4 sessions: costs [0.10, 0.20, 0.30, 1.00]
    # p75 index = int(4 * 0.75) = 3 → costs[3] = 1.00
    sessions = [
        _session(cost_usd=0.10, project="acme:auth"),
        _session(cost_usd=0.20),
        _session(cost_usd=0.30),
        _session(cost_usd=1.00),
    ]
    sig = detect_unattributed_high_cost(sessions)
    assert sig.available is True
    flagged_costs = {s.cost_usd for s in sig.sessions}
    assert 1.00 in flagged_costs
    # The $0.20 and $0.30 unattributed sessions are below p75
    assert 0.10 not in flagged_costs  # this one has project attribution


def test_unattributed_no_flag_when_all_attributed() -> None:
    sessions = [
        _session(cost_usd=0.50, project="acme:auth"),
        _session(cost_usd=1.00, project="acme:api"),
    ]
    sig = detect_unattributed_high_cost(sessions)
    assert sig.sessions == []
    assert sig.available is True


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def test_build_health_report_all_signals_present() -> None:
    sessions = [_session(tool_calls=10, tool_errors=5, project="acme:auth")]
    report = build_health_report(sessions, period="month")
    assert isinstance(report, WorkHealthReport)
    assert report.period == "month"
    assert report.session_count == 1
    assert len(report.signals) == 5
    categories = {s.category for s in report.signals}
    assert "high_error_rate" in categories
    assert "wall_vs_active" in categories
    assert "high_spend_low_delta" in categories
    assert "repeated_attempts" in categories
    assert "unattributed_high_cost" in categories


# ---------------------------------------------------------------------------
# CLI: text output
# ---------------------------------------------------------------------------


def test_health_cli_text_output(tmp_path: Any) -> None:
    from halyard.cli import app

    sessions = [
        _session(tool_calls=10, tool_errors=4, project="acme:auth"),
    ]
    runner = CliRunner()

    with (
        patch("halyard.ai_log.find_project_dir", return_value=tmp_path),
        patch("halyard.ai_log.parse_sessions", return_value=sessions),
    ):
        result = runner.invoke(app, ["health", "--period", "all"])

    assert result.exit_code == 0
    assert "AI Work Health" in result.output
    assert "These are operational signals, not productivity scores." in result.output


def test_health_cli_json_output(tmp_path: Any) -> None:
    from halyard.cli import app

    sessions = [_session(tool_calls=10, tool_errors=4, project="acme:auth")]
    runner = CliRunner()

    with (
        patch("halyard.ai_log.find_project_dir", return_value=tmp_path),
        patch("halyard.ai_log.parse_sessions", return_value=sessions),
    ):
        result = runner.invoke(app, ["health", "--period", "all", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["period"] == "all"
    assert "session_count" in data
    assert "signals" in data
    assert all("category" in s for s in data["signals"])
    assert all("available" in s for s in data["signals"])


def test_health_cli_exits_1_no_project() -> None:
    from halyard.cli import app

    runner = CliRunner()
    with (
        patch("halyard.ai_log.find_project_dir", return_value=None),
        patch("halyard.hub.find_hub", return_value=None),
    ):
        result = runner.invoke(app, ["health"])

    assert result.exit_code == 1
    assert "No Halyard project found" in result.output
