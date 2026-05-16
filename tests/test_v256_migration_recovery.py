"""v2.56 — partially-applied multi-statement migration self-heals (P1-b)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from halyard.db import _CURRENT_VERSION, get_db

# A pre-v3 ("version 2") sessions table: the v1 base columns minus
# everything the v2->v3 and v3->v4 migrations add.
_V2_SESSIONS = """
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    project     TEXT,
    tool        TEXT NOT NULL,
    model       TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT NOT NULL,
    input_tok   INTEGER NOT NULL DEFAULT 0,
    output_tok  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL NOT NULL DEFAULT 0,
    source_file TEXT NOT NULL
);
"""

_V3_COLUMNS = {
    "branch",
    "commit_count",
    "code_removed",
    "pr_ref",
    "pr_state",
    "outcome_resolved_at",
}


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}


def test_partial_v2_to_v3_migration_self_heals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "cache.db"
    monkeypatch.setattr("halyard.db._DB_PATH", db_file)

    # Simulate a crash mid v2->v3: version is still 2, but the FIRST
    # ALTER (branch) already landed; the rest never ran.
    conn = sqlite3.connect(str(db_file))
    conn.executescript(_V2_SESSIONS)
    conn.execute("ALTER TABLE sessions ADD COLUMN branch TEXT")
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
    conn.close()

    # Before: the recovery bug would hit "duplicate column: branch",
    # swallow it, skip the remaining ALTERs, and still bump to v3.
    healed = get_db()
    try:
        cols = _columns(healed)
        version = healed.execute("PRAGMA user_version").fetchone()[0]
    finally:
        healed.close()

    # Every v3 column present (not just `branch`) and v4 `code_added`.
    assert cols >= _V3_COLUMNS, f"missing: {_V3_COLUMNS - cols}"
    assert "code_added" in cols
    assert version == _CURRENT_VERSION


def test_clean_fresh_db_still_at_current_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("halyard.db._DB_PATH", tmp_path / "cache.db")
    conn = get_db()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = _columns(conn)
    finally:
        conn.close()
    assert version == _CURRENT_VERSION
    assert cols >= _V3_COLUMNS and "code_added" in cols
