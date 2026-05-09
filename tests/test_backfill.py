"""Tests for v2.13 — backtracking attribution."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, backfill_window
from halyard.cli import app

runner = CliRunner()


def _session(
    *,
    start: datetime,
    project: str | None = None,
    minutes: int = 30,
    tool: str = "claude-code",
    cost: float = 0.50,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=minutes),
        tool=tool,
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost,
        project=project,
    )


def _write_timeclock(path: Path, entries: list[tuple[datetime, datetime, str]]) -> None:
    lines = ["; Halyard timeclock"]
    for start, end, account in entries:
        lines.append(f"i {start:%Y-%m-%d %H:%M:%S} {account}")
        lines.append(f"o {end:%Y-%m-%d %H:%M:%S}")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# backfill_window unit tests
# ---------------------------------------------------------------------------


def test_backfill_window_attributes_sessions_in_range(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    session = _session(start=datetime(2026, 5, 8, 10, 30))
    append_session(tmp_path, session)

    count = backfill_window(tmp_path, t0, t1, "acme:auth")
    assert count == 1

    log = (tmp_path / AI_LOG_FILENAME).read_text()
    assert "project=acme:auth" in log


def test_backfill_window_ignores_sessions_outside_range(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    session = _session(start=datetime(2026, 5, 8, 14, 0))  # after window
    append_session(tmp_path, session)

    count = backfill_window(tmp_path, t0, t1, "acme:auth")
    assert count == 0


def test_backfill_window_skips_already_attributed(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    session = _session(start=datetime(2026, 5, 8, 10, 30), project="acme:other")
    append_session(tmp_path, session)

    count = backfill_window(tmp_path, t0, t1, "acme:auth")
    assert count == 0

    log = (tmp_path / AI_LOG_FILENAME).read_text()
    assert "project=acme:other" in log
    assert "project=acme:auth" not in log


def test_backfill_window_dry_run_does_not_write(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    session = _session(start=datetime(2026, 5, 8, 10, 30))
    append_session(tmp_path, session)
    original = (tmp_path / AI_LOG_FILENAME).read_text()

    count = backfill_window(tmp_path, t0, t1, "acme:auth", dry_run=True)
    assert count == 1
    assert (tmp_path / AI_LOG_FILENAME).read_text() == original


def test_backfill_window_boundary_start_inclusive(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    session = _session(start=t0)  # exactly at window start
    append_session(tmp_path, session)

    count = backfill_window(tmp_path, t0, t1, "acme:auth")
    assert count == 1


def test_backfill_window_boundary_end_exclusive(tmp_path: Path) -> None:
    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    session = _session(start=t1)  # exactly at window end — excluded
    append_session(tmp_path, session)

    count = backfill_window(tmp_path, t0, t1, "acme:auth")
    assert count == 0


def test_backfill_window_no_log_file(tmp_path: Path) -> None:
    t0, t1 = datetime(2026, 5, 8, 10, 0), datetime(2026, 5, 8, 12, 0)
    count = backfill_window(tmp_path, t0, t1, "acme:auth")
    assert count == 0


# ---------------------------------------------------------------------------
# halyard stop auto-attribution
# ---------------------------------------------------------------------------


def test_stop_attributes_sessions_in_window(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    tc = tmp_path / "time.timeclock"
    tc.write_text("; timeclock\n")

    # Write an unattributed session that started during the timer window
    session_start = datetime(2026, 5, 8, 10, 15)
    session = _session(start=session_start)
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "\n")
    append_session(tmp_path, session)

    from halyard.reports import _HALYARD_ACTIVE

    timer_start = datetime(2026, 5, 8, 10, 0)
    _HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    _HALYARD_ACTIVE.write_text(
        f"timeclock={tc}\nslug=acme:auth\nstarted={timer_start:%Y-%m-%d %H:%M:%S}\n"
    )
    tc.write_text(f"; timeclock\ni {timer_start:%Y-%m-%d %H:%M:%S} acme:auth\n")

    result = runner.invoke(app, ["stop"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Attributed 1 AI session" in result.output

    log = (tmp_path / AI_LOG_FILENAME).read_text()
    assert "project=acme:auth" in log


def test_stop_silent_when_no_sessions_in_window(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    tc = tmp_path / "time.timeclock"

    from halyard.reports import _HALYARD_ACTIVE

    timer_start = datetime(2026, 5, 8, 10, 0)
    _HALYARD_ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    _HALYARD_ACTIVE.write_text(
        f"timeclock={tc}\nslug=acme:auth\nstarted={timer_start:%Y-%m-%d %H:%M:%S}\n"
    )
    tc.write_text(f"; timeclock\ni {timer_start:%Y-%m-%d %H:%M:%S} acme:auth\n")

    result = runner.invoke(app, ["stop"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Attributed" not in result.output


# ---------------------------------------------------------------------------
# halyard backfill command
# ---------------------------------------------------------------------------


def test_backfill_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")

    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    _write_timeclock(tmp_path / "time.timeclock", [(t0, t1, "acme:auth")])

    session = _session(start=datetime(2026, 5, 8, 10, 30))
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "\n")
    append_session(tmp_path, session)
    original = (tmp_path / AI_LOG_FILENAME).read_text()

    result = runner.invoke(app, ["backfill", "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "would be attributed" in result.output
    assert (tmp_path / AI_LOG_FILENAME).read_text() == original


def test_backfill_attributes_unambiguous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")

    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    _write_timeclock(tmp_path / "time.timeclock", [(t0, t1, "acme:auth")])

    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "\n")
    append_session(tmp_path, _session(start=datetime(2026, 5, 8, 10, 30)))
    append_session(tmp_path, _session(start=datetime(2026, 5, 8, 11, 0)))

    result = runner.invoke(app, ["backfill"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "Attributed 2" in result.output

    log = (tmp_path / AI_LOG_FILENAME).read_text()
    assert log.count("project=acme:auth") == 2


def test_backfill_skips_ambiguous_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")

    t0 = datetime(2026, 5, 8, 10, 0)
    t1 = datetime(2026, 5, 8, 12, 0)
    # Two overlapping windows for different projects
    _write_timeclock(
        tmp_path / "time.timeclock",
        [(t0, t1, "acme:auth"), (t0, t1, "acme:other")],
    )

    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "\n")
    append_session(tmp_path, _session(start=datetime(2026, 5, 8, 10, 30)))

    result = runner.invoke(app, ["backfill"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "ambiguous" in result.output

    log = (tmp_path / AI_LOG_FILENAME).read_text()
    assert "project=" not in log


def test_backfill_no_timeclock_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    (tmp_path / "time.timeclock").write_text("; empty\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER + "\n")

    result = runner.invoke(app, ["backfill"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "No timeclock data" in result.output


# ---------------------------------------------------------------------------
# L-3: backfill_window uses atomic write (tmp → replace)
# ---------------------------------------------------------------------------


def test_backfill_window_atomic_write(tmp_path: Path) -> None:
    """backfill_window must write via a temp file then rename (no stale .tmp)."""
    from halyard.ai_log import parse_sessions

    start = datetime(2026, 5, 6, 10, 0)
    window_end = datetime(2026, 5, 6, 12, 0)

    log = tmp_path / AI_LOG_FILENAME
    append_session(tmp_path, _session(start=start))

    tmp_file = log.with_suffix(".log.tmp")
    assert not tmp_file.exists()

    changed = backfill_window(tmp_path, start, window_end, "acme:auth")

    assert changed == 1
    assert not tmp_file.exists()
    sessions = parse_sessions(tmp_path)
    assert sessions[0].project == "acme:auth"


def test_backfill_window_dry_run_leaves_no_tmp(tmp_path: Path) -> None:
    """In dry_run mode, no tmp file must be written."""
    from halyard.ai_log import parse_sessions

    start = datetime(2026, 5, 6, 10, 0)
    window_end = datetime(2026, 5, 6, 12, 0)

    append_session(tmp_path, _session(start=start))

    changed = backfill_window(
        tmp_path, start, window_end, "acme:auth", dry_run=True
    )

    log = tmp_path / AI_LOG_FILENAME
    assert changed == 1
    assert not log.with_suffix(".log.tmp").exists()
    # dry_run must not write attribution to disk
    sessions = parse_sessions(tmp_path)
    assert sessions[0].project is None
