"""Tests for v2.14 — SQLite read-model cache."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.cli import app
from halyard.db import SyncResult, get_db, last_sync, reset, sync_all

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect registry and hub so tests don't read real user data."""
    monkeypatch.setattr("halyard.registry.REGISTRY_PATH", tmp_path / ".halyard" / "projects")
    monkeypatch.setattr("halyard.hub.find_hub", lambda: None)


_SESSION_LINE_A = (
    "s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 "
    "10000 2000 0.0850 project=test:proj"
)
_SESSION_LINE_B = (
    "s 2026-01-02T10:00:00 2026-01-02T10:45:00 claude-code claude-sonnet-4-6 "
    "20000 4000 0.1700 project=test:proj"
)

_TIMECLOCK = """\
i 2026-01-01 09:00:00 test:proj
o 2026-01-01 09:30:00
i 2026-01-02 10:00:00 test:proj
o 2026-01-02 10:45:00
"""

_TIMECLOCK_OPEN = """\
i 2026-01-01 09:00:00 test:proj
o 2026-01-01 09:30:00
i 2026-01-02 10:00:00 test:proj
"""


def _setup_project(tmp_path: Path, session_lines: list[str], tc_text: str = "") -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")
    log = "; header\n" + "\n".join(session_lines) + "\n"
    (tmp_path / "ai-sessions.log").write_text(log)
    if tc_text:
        (tmp_path / "time.timeclock").write_text(tc_text)
    return tmp_path


# ---------------------------------------------------------------------------
# get_db / schema
# ---------------------------------------------------------------------------


def test_get_db_creates_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    conn = get_db()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    conn.close()
    assert {"sessions", "timeclock", "sync_log"} <= tables


# ---------------------------------------------------------------------------
# sync_all
# ---------------------------------------------------------------------------


def test_sync_all_loads_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A, _SESSION_LINE_B])

    result = sync_all()

    assert isinstance(result, SyncResult)
    assert result.sessions_added == 2
    assert result.files_read >= 1

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()
    assert count == 2


def test_sync_all_loads_timeclock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A], _TIMECLOCK)

    result = sync_all()

    assert result.timeclock_added == 2

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM timeclock").fetchone()[0]
    conn.close()
    assert count == 2


def test_sync_all_excludes_open_timeclock_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A], _TIMECLOCK_OPEN)

    result = sync_all()

    assert result.timeclock_added == 1  # only the closed entry


def test_sync_all_writes_sync_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A])

    sync_all()

    conn = get_db()
    row = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row is not None
    assert row["files_read"] >= 1


def test_sync_all_no_log_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    (tmp_path / "halyard.toml").write_text("[business]\nname = 'Test'\n")

    result = sync_all()
    assert result.sessions_added == 0
    assert result.files_read == 0


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_sync_all_idempotent_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A, _SESSION_LINE_B])

    r1 = sync_all()
    r2 = sync_all()

    assert r1.sessions_added == 2
    assert r2.sessions_added == 0  # nothing new on second sync

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()
    assert count == 2  # still exactly 2 rows


def test_sync_all_idempotent_timeclock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A], _TIMECLOCK)

    sync_all()
    sync_all()

    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM timeclock").fetchone()[0]
    conn.close()
    assert count == 2


# ---------------------------------------------------------------------------
# last_sync / reset
# ---------------------------------------------------------------------------


def test_last_sync_none_before_any_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    assert last_sync() is None


def test_last_sync_returns_row_after_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A])

    sync_all()
    row = last_sync()

    assert row is not None
    assert "synced_at" in row
    assert row["files_read"] >= 1


def test_reset_removes_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A])

    sync_all()
    assert (tmp_path / "cache.db").exists()

    reset()
    assert not (tmp_path / "cache.db").exists()
    assert last_sync() is None


# ---------------------------------------------------------------------------
# CLI: halyard db sync
# ---------------------------------------------------------------------------


def test_db_sync_cli_basic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A, _SESSION_LINE_B])

    result = runner.invoke(app, ["db", "sync"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "2" in result.output  # 2 sessions added


def test_db_sync_cli_status_no_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")

    result = runner.invoke(app, ["db", "sync", "--status"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "never" in result.output.lower() or "no sync" in result.output.lower()


def test_db_sync_cli_status_after_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A])

    sync_all()
    result = runner.invoke(app, ["db", "sync", "--status"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "2026" in result.output  # synced_at timestamp shown


# ---------------------------------------------------------------------------
# CLI: halyard db reset
# ---------------------------------------------------------------------------


def test_db_reset_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A])

    sync_all()
    assert (tmp_path / "cache.db").exists()

    result = runner.invoke(app, ["db", "reset"], catch_exceptions=False)

    assert result.exit_code == 0
    assert not (tmp_path / "cache.db").exists()


# ---------------------------------------------------------------------------
# Cache upsert — amendment data is written on re-sync (INSERT OR REPLACE)
# ---------------------------------------------------------------------------


def test_sync_applies_amendment_on_resync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-syncing after an amendment record is written updates the cached row."""
    from halyard.ai_log import session_hash

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    _setup_project(tmp_path, [_SESSION_LINE_A])

    # First sync — row has no pr_ref
    sync_all()
    conn = get_db()
    row = conn.execute("SELECT pr_ref FROM sessions WHERE project = 'test:proj'").fetchone()
    assert row["pr_ref"] is None
    conn.close()

    # Append an amendment record to the log
    line_hash = session_hash(_SESSION_LINE_A)
    amendment = (
        f"a {line_hash} pr_ref=org/repo#7 pr_state=merged outcome_resolved_at=2026-01-01T12:00:00"
    )
    log_path = tmp_path / "ai-sessions.log"
    log_path.write_text(log_path.read_text() + amendment + "\n")

    # Re-sync — amended pr_ref should be reflected in the cache
    sync_all()
    conn = get_db()
    row = conn.execute(
        "SELECT pr_ref, pr_state FROM sessions WHERE project = 'test:proj'"
    ).fetchone()
    assert row["pr_ref"] == "org/repo#7"
    assert row["pr_state"] == "merged"
    conn.close()
