"""Tests for the auto human timer (v2.28)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.auto_timer import (
    _AUTO_TIMER_FILE,
    _TS_FMT,
    auto_timer_activity,
    auto_timer_close_if_stale,
    auto_timer_close_now,
    auto_timer_update_activity,
)


@pytest.fixture(autouse=True)
def clean_auto_timer():
    _AUTO_TIMER_FILE.unlink(missing_ok=True)
    yield
    _AUTO_TIMER_FILE.unlink(missing_ok=True)


def _ts(dt: datetime) -> str:
    return dt.strftime(_TS_FMT)


def _read_state() -> dict[str, str]:
    lines = _AUTO_TIMER_FILE.read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def _read_tc(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# auto_timer_activity
# ---------------------------------------------------------------------------


def test_opens_new_timer(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    assert _AUTO_TIMER_FILE.exists()
    state = _read_state()
    assert state["project"] == "acme:web"
    assert state["started"] == _ts(t0)
    assert state["last_activity"] == _ts(t0)

    lines = _read_tc(tc)
    assert any(line.startswith("i") and "acme:web" in line and ";auto" in line for line in lines)


def test_updates_last_activity_when_already_open(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)
    t1 = datetime(2026, 5, 9, 14, 20, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)
        auto_timer_activity("acme:web", tc, now=t1)

    state = _read_state()
    assert state["last_activity"] == _ts(t1)
    # Only one i entry written
    assert sum(1 for line in _read_tc(tc) if line.startswith("i")) == 1


def test_skips_when_manual_timer_running(tmp_path):
    from halyard.reports import ActiveTimer

    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)
    fake_active = ActiveTimer(slug="manual:proj", timeclock=tc, started=_ts(t0))

    with patch("halyard.reports.read_active_timer", return_value=fake_active):
        auto_timer_activity("acme:web", tc, now=t0)

    assert not _AUTO_TIMER_FILE.exists()
    assert _read_tc(tc) == []


def test_skips_when_timeclock_missing(tmp_path):
    tc = tmp_path / "missing.timeclock"
    t0 = datetime(2026, 5, 9, 14, 0, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    assert not _AUTO_TIMER_FILE.exists()


# ---------------------------------------------------------------------------
# auto_timer_close_if_stale
# ---------------------------------------------------------------------------


def test_closes_stale_timer(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    t_stale = t0 + timedelta(minutes=31)
    closed = auto_timer_close_if_stale(now=t_stale)

    assert closed is True
    assert not _AUTO_TIMER_FILE.exists()
    lines = _read_tc(tc)
    assert any(line.startswith("o") and _ts(t0) in line for line in lines)


def test_does_not_close_active_timer(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    t_soon = t0 + timedelta(minutes=10)
    closed = auto_timer_close_if_stale(now=t_soon)

    assert closed is False
    assert _AUTO_TIMER_FILE.exists()
    assert not any(line.startswith("o") for line in _read_tc(tc))


def test_noop_when_no_state():
    closed = auto_timer_close_if_stale()
    assert closed is False


def test_stale_check_uses_last_activity_not_started(tmp_path):
    """A session with recent last_activity should stay open even if started long ago."""
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 10, 0, 0)
    t_recent = datetime(2026, 5, 9, 14, 55, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    auto_timer_update_activity(now=t_recent)

    t_check = t_recent + timedelta(minutes=10)
    closed = auto_timer_close_if_stale(now=t_check)
    assert closed is False


# ---------------------------------------------------------------------------
# auto_timer_close_now
# ---------------------------------------------------------------------------


def test_close_now_writes_clockout(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)
    t_stop = datetime(2026, 5, 9, 15, 30, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    closed = auto_timer_close_now(now=t_stop)

    assert closed is True
    assert not _AUTO_TIMER_FILE.exists()
    lines = _read_tc(tc)
    assert any(line.startswith("o") and _ts(t_stop) in line for line in lines)


def test_close_now_noop_when_nothing_open():
    closed = auto_timer_close_now()
    assert closed is False


# ---------------------------------------------------------------------------
# auto_timer_update_activity
# ---------------------------------------------------------------------------


def test_update_activity_refreshes_timestamp(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 14, 0, 0)
    t1 = datetime(2026, 5, 9, 14, 45, 0)

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    auto_timer_update_activity(now=t1)

    state = _read_state()
    assert state["last_activity"] == _ts(t1)
    # No extra timeclock entries
    assert sum(1 for line in _read_tc(tc) if line.startswith("i")) == 1


def test_update_activity_noop_when_nothing_open():
    auto_timer_update_activity()  # should not raise


# ---------------------------------------------------------------------------
# Presence window: gap detection
# ---------------------------------------------------------------------------


def test_new_session_after_gap_closes_old_and_opens_new(tmp_path):
    tc = tmp_path / "time.timeclock"
    tc.write_text("")
    t0 = datetime(2026, 5, 9, 10, 0, 0)
    t_gap = t0 + timedelta(minutes=35)  # > 30 min

    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t0)

    # Simulate gap then new session start
    auto_timer_close_if_stale(now=t_gap)
    with patch("halyard.reports.read_active_timer", return_value=None):
        auto_timer_activity("acme:web", tc, now=t_gap)

    lines = _read_tc(tc)
    i_lines = [line for line in lines if line.startswith("i")]
    o_lines = [line for line in lines if line.startswith("o")]
    assert len(i_lines) == 2
    assert len(o_lines) == 1
