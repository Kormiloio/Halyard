"""Tests for AI plan configuration parsing."""

from __future__ import annotations

from pathlib import Path

from halyard.ai_plans import AI_PLANS_FILENAME, read_ai_plans


def _write_plans(tmp_path: Path, content: str) -> None:
    (tmp_path / AI_PLANS_FILENAME).write_text(content)


def test_read_empty_file_returns_empty_list(tmp_path: Path) -> None:
    _write_plans(tmp_path, "")
    assert read_ai_plans(tmp_path) == []


def test_read_missing_file_returns_empty_list(tmp_path: Path) -> None:
    assert read_ai_plans(tmp_path) == []


def test_read_seat_plan(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "claude-max"
tool = "claude-code"
billing = "seat"
monthly_usd = 200.0
allocation = "active_minutes"
starts_on = "2026-05-01"
""",
    )
    plans = read_ai_plans(tmp_path)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.slug == "claude-max"
    assert plan.tool == "claude-code"
    assert plan.billing == "seat"
    assert plan.monthly_usd == 200.0
    assert plan.allocation == "active_minutes"
    assert plan.starts_on is not None
    assert plan.starts_on.year == 2026


def test_read_api_plan(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "anthropic-api"
tool = "claude-api"
billing = "api"
allocation = "direct"
""",
    )
    plans = read_ai_plans(tmp_path)
    assert len(plans) == 1
    assert plans[0].billing == "api"
    assert plans[0].monthly_usd is None


def test_read_credits_plan(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "cursor-pro"
tool = "cursor"
billing = "credits"
monthly_usd = 20.0
included_credits = 500
credit_to_usd = 0.04
allocation = "credits"
starts_on = "2026-05-01"
""",
    )
    plans = read_ai_plans(tmp_path)
    assert len(plans) == 1
    plan = plans[0]
    assert plan.billing == "credits"
    assert plan.included_credits == 500
    assert plan.credit_to_usd == 0.04


def test_read_multiple_plans(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "claude-max"
tool = "claude-code"
billing = "seat"
monthly_usd = 200.0
allocation = "active_minutes"

[[plan]]
slug = "anthropic-api"
tool = "claude-api"
billing = "api"
allocation = "direct"
""",
    )
    plans = read_ai_plans(tmp_path)
    assert len(plans) == 2
    assert plans[0].slug == "claude-max"
    assert plans[1].slug == "anthropic-api"


def test_is_active_in_covers_start_month(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "p"
tool = "t"
billing = "seat"
monthly_usd = 100.0
allocation = "active_minutes"
starts_on = "2026-05-01"
""",
    )
    plan = read_ai_plans(tmp_path)[0]
    assert plan.is_active_in(2026, 5) is True


def test_is_active_in_excludes_before_start(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "p"
tool = "t"
billing = "seat"
monthly_usd = 100.0
allocation = "active_minutes"
starts_on = "2026-06-01"
""",
    )
    plan = read_ai_plans(tmp_path)[0]
    assert plan.is_active_in(2026, 5) is False


def test_is_active_in_excludes_after_end(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "p"
tool = "t"
billing = "seat"
monthly_usd = 100.0
allocation = "active_minutes"
ends_on = "2026-04-30"
""",
    )
    plan = read_ai_plans(tmp_path)[0]
    assert plan.is_active_in(2026, 5) is False


def test_plan_with_no_dates_is_always_active(tmp_path: Path) -> None:
    _write_plans(
        tmp_path,
        """
[[plan]]
slug = "p"
tool = "t"
billing = "api"
allocation = "direct"
""",
    )
    plan = read_ai_plans(tmp_path)[0]
    assert plan.is_active_in(2020, 1) is True
    assert plan.is_active_in(2030, 12) is True
