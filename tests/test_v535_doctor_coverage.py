"""v5.35 — doctor checks for the two silent losses found in v5.26/v5.32.

Both are "Halyard's own signals disagree with each other", which is how every
defect in this track surfaced:

- counted human time far below AI session time is the signature of the
  pre-v5.26 auto-timer under-count;
- a transcript the collectors could only read part of is recorded in the
  diagnostic log and nowhere a user would look.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard import doctor

TS = "%Y-%m-%d %H:%M:%S"
ISO = "%Y-%m-%dT%H:%M:%S"


def _project(tmp_path: Path, *, human_hours: float, sessions: list[tuple[datetime, datetime]]):
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    rows = ["; halyard\n"]
    for start, end in sessions:
        rows.append(
            f"s {start.strftime(ISO)} {end.strftime(ISO)} claude-code claude-opus-5 "
            "100 50 0.0 project=acme:web\n"
        )
    (tmp_path / "ai-sessions.log").write_text("".join(rows), encoding="utf-8")

    base = datetime(2026, 8, 11, 1, 0, 0)
    tc = ["; timeclock\n"]
    if human_hours:
        tc.append(f"i {base.strftime(TS)} acme:web  ;auto\n")
        tc.append(f"o {(base + timedelta(hours=human_hours)).strftime(TS)}\n")
    (tmp_path / "time.timeclock").write_text("".join(tc), encoding="utf-8")
    return tmp_path


def _hours(n: int, start_hour: int = 8) -> list[tuple[datetime, datetime]]:
    """n one-hour sessions on consecutive days — all well under the 12 h bound."""
    return [
        (
            datetime(2026, 8, 1) + timedelta(days=i, hours=start_hour),
            datetime(2026, 8, 1) + timedelta(days=i, hours=start_hour + 1),
        )
        for i in range(n)
    ]


# --- human-time coverage ----------------------------------------------


def test_fires_on_an_under_counted_timeclock(tmp_path: Path) -> None:
    """The observed shape: hours of recorded sessions, minutes counted."""
    p = _project(tmp_path, human_hours=0.5, sessions=_hours(10))
    checks = doctor._human_time_coverage_checks(p, None)

    assert len(checks) == 1
    assert checks[0].id == "timeclock.coverage"
    assert checks[0].status == "warning"
    assert "repair --from-sessions" in (checks[0].fix or "")


def test_silent_when_coverage_is_healthy(tmp_path: Path) -> None:
    p = _project(tmp_path, human_hours=8, sessions=_hours(10))
    assert doctor._human_time_coverage_checks(p, None) == []


def test_silent_on_a_short_day(tmp_path: Path) -> None:
    """Below the evidence floor there is nothing to judge.

    Without this a brand-new install with one 20-minute session and no
    timeclock would warn on day one.
    """
    p = _project(
        tmp_path,
        human_hours=0,
        sessions=[(datetime(2026, 8, 1, 9), datetime(2026, 8, 1, 9, 20))],
    )
    assert doctor._human_time_coverage_checks(p, None) == []


def test_a_long_lived_session_does_not_trip_the_check(tmp_path: Path) -> None:
    """The tuning finding, pinned.

    A single long-lived *imported* rollout (653 h observed) swamps the
    denominator. Counted unbounded, a machine whose timeclock is entirely
    correct reads ~9% coverage and fires; bounded, the same machine reads
    ~80%. The bound is what makes this check worth shipping — the v5.26
    design made tuning against real data a precondition for exactly this
    reason.
    """
    long_session = (datetime(2026, 8, 9, 13), datetime(2026, 9, 5, 18))  # 653 h
    p = _project(tmp_path, human_hours=8, sessions=[*_hours(10), long_session])

    assert doctor._human_time_coverage_checks(p, None) == [], (
        "a >12h session must be excluded from the denominator"
    )


def test_no_timeclock_is_not_a_finding(tmp_path: Path) -> None:
    p = _project(tmp_path, human_hours=8, sessions=_hours(10))
    (p / "time.timeclock").unlink()
    assert doctor._human_time_coverage_checks(p, None) == []


def test_no_target_directory_is_not_a_finding() -> None:
    assert doctor._human_time_coverage_checks(None, None) == []


# --- truncated transcripts --------------------------------------------


def test_truncation_in_the_log_is_surfaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "diagnostic.log"
    log.write_text(
        "[2026-09-05T10:00:00+00:00] codex rollout: big.jsonl exceeded the "
        "1073741824 byte budget after 1073741900 bytes — captured only up to that point\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("halyard.ai_log._HALYARD_DIAG_LOG", log)

    checks = doctor._truncated_transcript_checks()

    assert len(checks) == 1
    assert checks[0].id == "capture.truncated"
    assert checks[0].status == "warning"
    assert "big.jsonl" in checks[0].detail


def test_an_unrelated_log_is_not_a_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "diagnostic.log"
    log.write_text(
        "[2026-09-05T10:00:00+00:00] hub_client: request failed: Connection refused\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("halyard.ai_log._HALYARD_DIAG_LOG", log)
    assert doctor._truncated_transcript_checks() == []


def test_a_missing_log_is_not_a_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("halyard.ai_log._HALYARD_DIAG_LOG", tmp_path / "nope.log")
    assert doctor._truncated_transcript_checks() == []


# --- exit-code contract -----------------------------------------------


def test_neither_check_can_flip_the_exit_code(tmp_path: Path) -> None:
    """Both are `warning`. Reports stay usable; these are advisory."""
    p = _project(tmp_path, human_hours=0.5, sessions=_hours(10))
    for check in doctor._human_time_coverage_checks(p, None):
        assert check.status == "warning"
