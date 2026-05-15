"""Tests for v3.0 dashboard Leverage panel."""

from __future__ import annotations

from datetime import datetime, timedelta

from halyard.ai_log import AiSession
from halyard.dashboard import _leverage_panel


def _s(*, start: datetime, pr_state: str | None = None, pr_ref: str | None = None) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=10),
        tool="claude-code",
        model="sonnet",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        pr_state=pr_state,
        pr_ref=pr_ref,
    )


def test_empty_state() -> None:
    now = datetime(2026, 5, 14, 12)
    html = _leverage_panel([], now)
    assert "No sessions in the last 30 days" in html


def test_pct_calculation_all_merged() -> None:
    now = datetime(2026, 5, 14, 12)
    sessions = [
        _s(start=now - timedelta(days=1), pr_state="merged", pr_ref="o/r#1"),
        _s(start=now - timedelta(days=2), pr_state="merged", pr_ref="o/r#2"),
    ]
    html = _leverage_panel(sessions, now)
    assert "100%" in html
    assert "leverage-high" in html


def test_pct_calculation_mixed_mid_range() -> None:
    """1 merged of 4 = 25% → mid band (>=20)."""
    now = datetime(2026, 5, 14, 12)
    sessions = [
        _s(start=now - timedelta(days=1), pr_state="merged"),
        _s(start=now - timedelta(days=2), pr_state="open"),
        _s(start=now - timedelta(days=3), pr_state="closed"),
        _s(start=now - timedelta(days=4), pr_state="none"),
    ]
    html = _leverage_panel(sessions, now)
    assert "25%" in html
    assert "leverage-mid" in html


def test_pct_calculation_low_band() -> None:
    """1 merged of 10 = 10% → low band (<20)."""
    now = datetime(2026, 5, 14, 12)
    sessions = [
        _s(start=now - timedelta(days=1), pr_state="merged"),
        *[_s(start=now - timedelta(days=i + 2), pr_state="none") for i in range(9)],
    ]
    html = _leverage_panel(sessions, now)
    assert "10%" in html
    assert "leverage-low" in html


def test_old_sessions_excluded_from_30d_window() -> None:
    now = datetime(2026, 5, 14, 12)
    sessions = [
        _s(start=now - timedelta(days=1), pr_state="merged"),
        # ancient session — outside 30d window
        _s(start=now - timedelta(days=90), pr_state="open"),
    ]
    html = _leverage_panel(sessions, now)
    # Only the recent merged session counts → 100%
    assert "100%" in html


def test_unsynced_hint_shown_when_unresolved_sessions_exist() -> None:
    now = datetime(2026, 5, 14, 12)
    sessions = [_s(start=now - timedelta(days=1))]  # no pr_state
    html = _leverage_panel(sessions, now)
    assert "halyard outcome sync" in html


def test_no_unsynced_hint_when_everything_resolved() -> None:
    now = datetime(2026, 5, 14, 12)
    sessions = [
        _s(start=now - timedelta(days=1), pr_state="merged"),
        _s(start=now - timedelta(days=2), pr_state="none"),
    ]
    html = _leverage_panel(sessions, now)
    assert "halyard outcome sync" not in html
