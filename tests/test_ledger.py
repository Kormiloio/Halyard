"""Tests for the AI Work Ledger cost allocation engine."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from halyard.ai_log import AiSession
from halyard.ai_plans import AiPlan
from halyard.ledger import build_ledger


def _session(
    project: str | None = "acme:auth",
    tool: str = "claude-code",
    cost: float = 1.0,
    minutes: int = 10,
    credits: int | None = None,
) -> AiSession:
    start = datetime(2026, 5, 7, 10, 0)
    end = start + timedelta(minutes=minutes)
    return AiSession(
        start=start,
        end=end,
        tool=tool,
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost,
        project=project,
        credits=credits,
    )


def _api_plan(tool: str = "claude-api") -> AiPlan:
    return AiPlan(slug="api", tool=tool, billing="api", allocation="direct")


def _seat_plan(
    tool: str = "claude-code",
    monthly_usd: float = 200.0,
    allocation: str = "active_minutes",
) -> AiPlan:
    return AiPlan(
        slug="seat",
        tool=tool,
        billing="seat",
        monthly_usd=monthly_usd,
        allocation=allocation,  # type: ignore[arg-type]
    )


def _credits_plan(
    tool: str = "cursor",
    monthly_usd: float = 20.0,
    credit_to_usd: float = 0.04,
) -> AiPlan:
    return AiPlan(
        slug="credits",
        tool=tool,
        billing="credits",
        monthly_usd=monthly_usd,
        credit_to_usd=credit_to_usd,
        allocation="credits",
    )


# ---------------------------------------------------------------------------
# Direct API billing
# ---------------------------------------------------------------------------


def test_direct_api_uses_captured_cost() -> None:
    sessions = [_session(tool="claude-api", cost=2.50)]
    summary = build_ledger(sessions, [_api_plan()], [], year=2026, month=5)

    assert len(summary.entries) == 1
    entry = summary.entries[0]
    assert entry.direct_usd == pytest.approx(2.50)
    assert entry.allocated_usd == 0.0
    assert entry.total_usd == pytest.approx(2.50)
    assert entry.trust == "captured"


def test_no_plans_falls_back_to_direct() -> None:
    sessions = [_session(cost=1.0)]
    summary = build_ledger(sessions, [], [], year=2026, month=5)

    assert summary.entries[0].direct_usd == pytest.approx(1.0)
    assert summary.total_direct_usd == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Seat billing — active_minutes allocation
# ---------------------------------------------------------------------------


def test_seat_active_minutes_allocates_proportionally() -> None:
    # Two sessions: 10 min and 30 min → 25% and 75% of $200
    sessions = [
        _session(project="acme:auth", tool="claude-code", cost=0.0, minutes=10),
        _session(project="acme:dash", tool="claude-code", cost=0.0, minutes=30),
    ]
    plan = _seat_plan(monthly_usd=200.0, allocation="active_minutes")
    summary = build_ledger(sessions, [plan], [], year=2026, month=5)

    by_project = {e.project: e for e in summary.entries}
    assert by_project["acme:auth"].allocated_usd == pytest.approx(50.0, abs=0.01)
    assert by_project["acme:dash"].allocated_usd == pytest.approx(150.0, abs=0.01)
    assert summary.total_allocated_usd == pytest.approx(200.0, abs=0.01)


def test_seat_session_count_allocates_evenly() -> None:
    sessions = [
        _session(project="acme:auth", tool="claude-code", cost=0.0),
        _session(project="acme:auth", tool="claude-code", cost=0.0),
        _session(project="globex:reports", tool="claude-code", cost=0.0),
    ]
    plan = _seat_plan(monthly_usd=120.0, allocation="session_count")
    summary = build_ledger(sessions, [plan], [], year=2026, month=5)

    by_project = {e.project: e for e in summary.entries}
    assert by_project["acme:auth"].allocated_usd == pytest.approx(80.0, abs=0.01)
    assert by_project["globex:reports"].allocated_usd == pytest.approx(40.0, abs=0.01)


def test_seat_manual_allocation_produces_zero_cost() -> None:
    sessions = [_session(tool="claude-code", cost=0.0)]
    plan = _seat_plan(monthly_usd=200.0, allocation="manual")
    summary = build_ledger(sessions, [plan], [], year=2026, month=5)

    assert summary.entries[0].allocated_usd == 0.0
    assert summary.entries[0].trust == "unallocated"


def test_seat_zero_monthly_produces_zero_allocation() -> None:
    sessions = [_session(tool="claude-code", cost=0.0)]
    plan = _seat_plan(monthly_usd=0.0)
    summary = build_ledger(sessions, [plan], [], year=2026, month=5)

    assert summary.entries[0].allocated_usd == 0.0


# ---------------------------------------------------------------------------
# Credits billing
# ---------------------------------------------------------------------------


def test_credits_billing_uses_per_session_credits() -> None:
    sessions = [_session(tool="cursor", cost=0.0, credits=10)]
    plan = _credits_plan(credit_to_usd=0.04)
    summary = build_ledger(sessions, [plan], [], year=2026, month=5)

    assert summary.entries[0].allocated_usd == pytest.approx(0.40, abs=1e-4)


def test_credits_billing_falls_back_to_minutes_when_no_credits_field() -> None:
    # No credits field on session → fall back to minute-based allocation from monthly_usd
    sessions = [_session(tool="cursor", cost=0.0, credits=None, minutes=60)]
    plan = _credits_plan(monthly_usd=20.0)
    summary = build_ledger(sessions, [plan], [], year=2026, month=5)

    assert summary.entries[0].allocated_usd == pytest.approx(20.0, abs=0.01)


# ---------------------------------------------------------------------------
# Mixed plans (api + seat)
# ---------------------------------------------------------------------------


def test_mixed_plans_separate_direct_and_allocated() -> None:
    api_session = _session(project="acme:auth", tool="claude-api", cost=3.0)
    seat_session = _session(project="acme:auth", tool="claude-code", cost=0.0, minutes=60)
    plans = [_api_plan(), _seat_plan(monthly_usd=60.0, allocation="active_minutes")]
    summary = build_ledger([api_session, seat_session], plans, [], year=2026, month=5)

    entry = summary.entries[0]
    assert entry.direct_usd == pytest.approx(3.0)
    assert entry.allocated_usd == pytest.approx(60.0, abs=0.01)
    assert entry.trust == "mixed"


def test_summary_totals_are_correct() -> None:
    sessions = [
        _session(project="acme:auth", tool="claude-api", cost=5.0),
        _session(project="globex:reports", tool="claude-api", cost=3.0),
    ]
    summary = build_ledger(sessions, [_api_plan()], [], year=2026, month=5)

    assert summary.total_direct_usd == pytest.approx(8.0)
    assert summary.total_allocated_usd == 0.0
    assert summary.total_usd == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Timeclock attribution inference
# ---------------------------------------------------------------------------


def test_timeclock_overlap_infers_project_for_unattributed_session() -> None:
    session = _session(project=None, tool="claude-code", cost=0.0)
    # Timeclock entry that fully covers the session window
    tc_entries = [(datetime(2026, 5, 7, 9, 0), datetime(2026, 5, 7, 11, 0), "acme:auth")]

    summary = build_ledger([session], [], tc_entries, year=2026, month=5)

    assert len(summary.entries) == 1
    assert summary.entries[0].project == "acme:auth"
    assert summary.entries[0].has_inferred_attribution is True


def test_ambiguous_timeclock_overlap_leaves_session_unattributed() -> None:
    session = _session(project=None, tool="claude-code", cost=0.0)
    tc_entries = [
        (datetime(2026, 5, 7, 9, 0), datetime(2026, 5, 7, 11, 0), "acme:auth"),
        (datetime(2026, 5, 7, 9, 30), datetime(2026, 5, 7, 10, 30), "globex:reports"),
    ]
    summary = build_ledger([session], [], tc_entries, year=2026, month=5)

    assert summary.entries[0].project == "(unattributed)"
    assert summary.entries[0].has_inferred_attribution is False


def test_no_timeclock_overlap_leaves_session_unattributed() -> None:
    session = _session(project=None, tool="claude-code", cost=0.0)
    tc_entries = [(datetime(2026, 5, 7, 12, 0), datetime(2026, 5, 7, 13, 0), "acme:auth")]

    summary = build_ledger([session], [], tc_entries, year=2026, month=5)

    assert summary.entries[0].project == "(unattributed)"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_sessions_returns_empty_summary() -> None:
    summary = build_ledger([], [], [], year=2026, month=5)
    assert summary.entries == []
    assert summary.total_usd == 0.0


def test_period_label_format() -> None:
    summary = build_ledger([], [], [], year=2026, month=5)
    assert summary.period_label == "May 2026"


def test_unattributed_count_is_correct() -> None:
    sessions = [
        _session(project="acme:auth", cost=1.0),
        _session(project=None, cost=0.0),
        _session(project=None, cost=0.0),
    ]
    summary = build_ledger(sessions, [], [], year=2026, month=5)
    assert summary.unattributed_count == 1  # one "(unattributed)" bucket


# ---------------------------------------------------------------------------
# Trust label coverage
# ---------------------------------------------------------------------------


def test_trust_label_allocated_for_seat_only() -> None:
    """Seat-billed sessions with no direct cost produce 'allocated' trust."""
    sessions = [_session(tool="claude-code", cost=0.0, minutes=60)]
    summary = build_ledger(sessions, [_seat_plan(monthly_usd=60.0)], [], year=2026, month=5)
    assert summary.entries[0].trust == "allocated"


def test_trust_label_mixed_for_direct_and_allocated() -> None:
    """Both direct API and seat costs in same project → 'mixed'."""
    sessions = [
        _session(project="acme:auth", tool="claude-api", cost=5.0),
        _session(project="acme:auth", tool="claude-code", cost=0.0, minutes=60),
    ]
    summary = build_ledger(
        sessions,
        [_api_plan(), _seat_plan(monthly_usd=60.0)],
        [],
        year=2026,
        month=5,
    )
    entry = summary.entries[0]
    assert entry.trust == "mixed"
