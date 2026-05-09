"""Test backfill for backfill_window edge cases (v2.18 tasks 7.1-7.4)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, backfill_window, parse_sessions


def _session(start: str, end: str, project: str | None = None) -> str:
    proj = f" project={project}" if project else ""
    return f"s {start} {end} claude-code claude-sonnet-4-6 1000 200 0.01{proj}"


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _make_log(tmp_path: Path, lines: list[str]) -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\nname='T'\n")
    log = HEADER + "\n".join(lines) + "\n"
    (tmp_path / AI_LOG_FILENAME).write_text(log)
    return tmp_path


# ---------------------------------------------------------------------------
# 7.1: Session straddles midnight — window includes both halves
# ---------------------------------------------------------------------------


def test_backfill_session_straddles_midnight(tmp_path: Path) -> None:
    # Session runs 23:30 → 00:30 across midnight; window is 23:00 → 01:00
    s = _session("2026-05-01T23:30:00", "2026-05-02T00:30:00")
    _make_log(tmp_path, [s])

    count = backfill_window(
        tmp_path,
        _dt("2026-05-01T23:00:00"),
        _dt("2026-05-02T01:00:00"),
        "acme:auth",
    )

    assert count == 1
    sessions = list(parse_sessions(tmp_path))
    assert any(s.project == "acme:auth" for s in sessions)


# ---------------------------------------------------------------------------
# 7.2: Session start equals window end — not included
# ---------------------------------------------------------------------------


def test_backfill_session_at_window_boundary_excluded(tmp_path: Path) -> None:
    # Session starts exactly at window end → must NOT be included (start < end, not <=)
    s = _session("2026-05-01T10:00:00", "2026-05-01T10:30:00")
    _make_log(tmp_path, [s])

    count = backfill_window(
        tmp_path,
        _dt("2026-05-01T09:00:00"),
        _dt("2026-05-01T10:00:00"),  # window ends exactly at session start
        "acme:auth",
    )

    assert count == 0


# ---------------------------------------------------------------------------
# 7.3: Multiple overlapping i/o pairs — backfill attributes unattributed only
# ---------------------------------------------------------------------------


def test_backfill_attributes_only_unattributed(tmp_path: Path) -> None:
    attributed = _session("2026-05-01T09:00:00", "2026-05-01T09:30:00", project="existing:proj")
    unattributed = _session("2026-05-01T09:05:00", "2026-05-01T09:20:00")
    _make_log(tmp_path, [attributed, unattributed])

    count = backfill_window(
        tmp_path,
        _dt("2026-05-01T09:00:00"),
        _dt("2026-05-01T10:00:00"),
        "acme:auth",
    )

    # Only the unattributed session should be attributed
    assert count == 1
    sessions = list(parse_sessions(tmp_path))
    projects = [s.project for s in sessions]
    assert "existing:proj" in projects
    assert "acme:auth" in projects


# ---------------------------------------------------------------------------
# 7.4: Empty window — no error, returns 0
# ---------------------------------------------------------------------------


def test_backfill_empty_window_returns_zero(tmp_path: Path) -> None:
    _make_log(tmp_path, [])

    count = backfill_window(
        tmp_path,
        _dt("2026-05-01T09:00:00"),
        _dt("2026-05-01T10:00:00"),
        "acme:auth",
    )

    assert count == 0


def test_backfill_no_matching_sessions_returns_zero(tmp_path: Path) -> None:
    s = _session("2026-05-01T14:00:00", "2026-05-01T14:30:00")
    _make_log(tmp_path, [s])

    count = backfill_window(
        tmp_path,
        _dt("2026-05-01T09:00:00"),
        _dt("2026-05-01T10:00:00"),  # session is outside this window
        "acme:auth",
    )

    assert count == 0


def test_backfill_dry_run_does_not_write(tmp_path: Path) -> None:
    s = _session("2026-05-01T09:10:00", "2026-05-01T09:40:00")
    _make_log(tmp_path, [s])
    before = (tmp_path / AI_LOG_FILENAME).read_text()

    count = backfill_window(
        tmp_path,
        _dt("2026-05-01T09:00:00"),
        _dt("2026-05-01T10:00:00"),
        "acme:auth",
        dry_run=True,
    )

    assert count == 1
    assert (tmp_path / AI_LOG_FILENAME).read_text() == before  # file unchanged
