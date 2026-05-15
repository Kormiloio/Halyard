"""SQLite read-model cache for Halyard plain-text logs.

The plain-text files remain the source of truth. This module provides a
derived cache for faster queries. It is safe to delete cache.db at any time
and rebuild with `halyard db sync`.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_DB_PATH = Path.home() / ".halyard" / "cache.db"

# Schema version this code expects. Bump whenever a migration is added.
_CURRENT_VERSION = 4

# Initial schema for a fresh database — always reflects _CURRENT_VERSION.
_CREATE_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    project             TEXT,
    tool                TEXT NOT NULL,
    model               TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    ended_at            TEXT NOT NULL,
    input_tok           INTEGER NOT NULL DEFAULT 0,
    output_tok          INTEGER NOT NULL DEFAULT 0,
    cache_read          INTEGER,
    cache_write         INTEGER,
    cost_usd            REAL NOT NULL DEFAULT 0,
    tool_calls          INTEGER,
    tool_errors         INTEGER,
    source_file         TEXT NOT NULL,
    branch              TEXT,
    commit_count        INTEGER,
    code_added          INTEGER,
    code_removed        INTEGER,
    pr_ref              TEXT,
    pr_state            TEXT,
    outcome_resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS timeclock (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    source_file TEXT NOT NULL,
    UNIQUE(source_file, started_at, project)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at   TEXT NOT NULL,
    files_read  INTEGER NOT NULL,
    rows_added  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    session_id  TEXT PRIMARY KEY,
    pr_ref      TEXT,
    pr_state    TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS pr_cache (
    cache_key   TEXT PRIMARY KEY,
    payload     TEXT,
    fetched_at  TEXT
);
"""

# Each tuple is (from_version, sql_or_sentinel).
# Use the sentinel "REQUIRES_RESET" to tell users to run `halyard db reset`.
_MIGRATIONS: list[tuple[int, str]] = [
    # v0 → v1: establishes the migration framework; no schema change needed.
    (0, "-- no-op"),
    # v1 → v2: session IDs changed from sha256(raw_line) to content-addressed hash.
    #           Existing rows have stale IDs; user must reset the cache.
    (1, "REQUIRES_RESET"),
    # v2 → v3: v2.24 outcome metadata — new columns on sessions, outcomes + pr_cache tables.
    (
        2,
        """
ALTER TABLE sessions ADD COLUMN branch TEXT;
ALTER TABLE sessions ADD COLUMN commit_count INTEGER;
ALTER TABLE sessions ADD COLUMN code_removed INTEGER;
ALTER TABLE sessions ADD COLUMN pr_ref TEXT;
ALTER TABLE sessions ADD COLUMN pr_state TEXT;
ALTER TABLE sessions ADD COLUMN outcome_resolved_at TEXT;

CREATE TABLE IF NOT EXISTS outcomes (
    session_id  TEXT PRIMARY KEY,
    pr_ref      TEXT,
    pr_state    TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS pr_cache (
    cache_key   TEXT PRIMARY KEY,
    payload     TEXT,
    fetched_at  TEXT
);
""",
    ),
    # v3 → v4: add code_added column (was in AiSession but omitted from the v3 migration).
    (3, "ALTER TABLE sessions ADD COLUMN code_added INTEGER;"),
]


@dataclass
class SyncResult:
    sessions_added: int
    timeclock_added: int
    files_read: int
    synced_at: datetime


def db_path() -> Path:
    return _DB_PATH


def get_db() -> sqlite3.Connection:
    """Open (and migrate if needed) the cache database.

    On a fresh database, creates the schema at _CURRENT_VERSION.
    On an existing database, runs any pending migrations in order.
    Raises SystemExit if the database requires a manual reset.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row

    version: int = conn.execute("PRAGMA user_version").fetchone()[0]

    if version == 0:
        # Check if tables exist (old pre-migration database vs. fresh install).
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "sessions" not in tables:
            # Fresh database — create schema directly at current version.
            conn.executescript(_CREATE_SCHEMA_V1)
            conn.execute(f"PRAGMA user_version = {_CURRENT_VERSION}")
            conn.commit()
            return conn
        # Else: old database without version tracking — treat as v0.

    if version > _CURRENT_VERSION:
        conn.close()
        raise SystemExit(
            f"Cache database is version {version} but this Halyard installation "
            f"only understands up to version {_CURRENT_VERSION}. "
            "Upgrade Halyard or run `halyard db reset`."
        )

    # Run pending migrations.
    for from_version, sql in _MIGRATIONS:
        if version <= from_version:
            if sql == "REQUIRES_RESET":
                conn.close()
                raise SystemExit(
                    "Cache schema changed in v2.18 (session IDs are now content-addressed). "
                    "Run `halyard db reset` then `halyard db sync` to rebuild the cache. "
                    "No plain-text data is lost."
                )
            if sql.strip() and sql.strip() != "-- no-op":
                try:
                    conn.executescript(sql)
                except sqlite3.OperationalError as exc:
                    # A prior run may have died after applying an ALTER but
                    # before bumping user_version. Re-running the ALTER then
                    # fails with "duplicate column name" — treat that as
                    # already-applied so the migration self-heals instead of
                    # bricking the cache forever. Any other error is real.
                    if "duplicate column name" not in str(exc).lower():
                        conn.rollback()
                        conn.close()
                        raise
            conn.execute(f"PRAGMA user_version = {from_version + 1}")
            conn.commit()
            version = from_version + 1

    return conn


def sync_all() -> SyncResult:
    """Sync all known project and hub log files into the cache.

    Discovery order (per v2.18 spec):
    1. ~/.halyard/projects registry
    2. find_hub() if not already covered
    3. find_project_dir() (CWD walk-up) if not already covered
    """
    from halyard.ai_log import AI_LOG_FILENAME, find_project_dir
    from halyard.hub import find_hub
    from halyard.registry import read_registry, stale_paths

    sources: set[Path] = set()

    for p in read_registry():
        sources.add(p)

    hub_dir = find_hub()
    if hub_dir:
        sources.add(hub_dir)

    project_dir = find_project_dir()
    if project_dir:
        sources.add(project_dir)

    stale = stale_paths()
    if stale:
        from rich.console import Console as _Console

        _Console().print(
            "[yellow]Warning:[/] " + str(len(stale)) + " registered project(s) no longer found."
            " Run [bold]halyard projects list[/] to review."
        )

    conn = get_db()
    sessions_added = timeclock_added = files_read = 0

    try:
        for source in sorted(sources):
            log_path = source / AI_LOG_FILENAME
            if log_path.exists():
                files_read += 1
                sessions_added += _sync_sessions(conn, log_path)

            tc_path = source / "time.timeclock"
            if tc_path.exists():
                files_read += 1
                timeclock_added += _sync_timeclock(conn, tc_path)

        now = datetime.now()
        conn.execute(
            "INSERT INTO sync_log (synced_at, files_read, rows_added) VALUES (?, ?, ?)",
            (now.isoformat(), files_read, sessions_added + timeclock_added),
        )
        conn.commit()
    finally:
        conn.close()

    return SyncResult(
        sessions_added=sessions_added,
        timeclock_added=timeclock_added,
        files_read=files_read,
        synced_at=datetime.now(),
    )


def last_sync() -> dict[str, object] | None:
    """Return the most recent sync_log row as a dict, or None if never synced."""
    if not _DB_PATH.exists():
        return None
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def reset() -> None:
    """Delete the cache database."""
    if _DB_PATH.exists():
        _DB_PATH.unlink()


def _session_id(
    start: str, end: str, tool: str, model: str, input_tok: int, output_tok: int
) -> str:
    """Content-addressed session ID — stable across attribution amendments.

    Hashes only the immutable identity fields so that `a` amendment records
    (which change project/branch/etc.) never produce a duplicate cache row.
    """
    key = f"{start}|{end}|{tool}|{model}|{input_tok}|{output_tok}"
    return hashlib.sha256(key.encode()).hexdigest()


def _sync_sessions(conn: sqlite3.Connection, log_path: Path) -> int:
    # Use parse_sessions (not _parse_line) so amendment records are folded in.
    # INSERT OR REPLACE ensures re-syncing after an amendment updates the cache row.
    from halyard.ai_log import parse_sessions

    upserted = 0
    source = str(log_path.resolve())
    sessions = parse_sessions(log_path.parent)

    for session in sessions:
        sid = _session_id(
            session.start.isoformat(),
            session.end.isoformat(),
            session.tool,
            session.model,
            session.input_tokens,
            session.output_tokens,
        )

        is_new = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (sid,)).fetchone() is None

        conn.execute(
            """
            INSERT OR REPLACE INTO sessions
                (id, project, tool, model, started_at, ended_at,
                 input_tok, output_tok, cache_read, cache_write,
                 cost_usd, tool_calls, tool_errors, source_file,
                 branch, commit_count, code_added, code_removed,
                 pr_ref, pr_state, outcome_resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                session.project,
                session.tool,
                session.model,
                session.start.isoformat(),
                session.end.isoformat(),
                session.input_tokens,
                session.output_tokens,
                session.cache_read,
                session.cache_write,
                session.cost_usd,
                session.tool_calls,
                session.tool_errors,
                source,
                session.branch,
                session.commit_count,
                session.code_added,
                session.code_removed,
                session.pr_ref,
                session.pr_state,
                session.outcome_resolved_at,
            ),
        )
        if is_new:
            upserted += 1

    return upserted


def _sync_timeclock(conn: sqlite3.Connection, tc_path: Path) -> int:
    """Sync only closed timeclock entries (open entries are excluded)."""
    added = 0
    source = str(tc_path.resolve())

    for start, end, account in _parse_closed_timeclock(tc_path):
        # Pre-check existence: INSERT OR REPLACE always reports rowcount=1
        # (it deletes+inserts), so without this a resync of unchanged
        # entries would overcount "added". Mirrors the sessions path.
        is_new = (
            conn.execute(
                "SELECT 1 FROM timeclock WHERE source_file = ? AND started_at = ? AND project = ?",
                (source, start.isoformat(), account),
            ).fetchone()
            is None
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO timeclock
                (project, started_at, ended_at, source_file)
            VALUES (?, ?, ?, ?)
            """,
            (account, start.isoformat(), end.isoformat(), source),
        )
        if is_new:
            added += 1

    return added


def _parse_closed_timeclock(tc_path: Path) -> list[tuple[datetime, datetime, str]]:
    """Parse only completed i/o pairs from a timeclock file."""
    entries: list[tuple[datetime, datetime, str]] = []
    open_entry: tuple[datetime, str] | None = None

    for raw_line in tc_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        marker, day, time_part = parts[0], parts[1], parts[2]
        try:
            ts = datetime.strptime(f"{day} {time_part}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if marker == "i" and len(parts) >= 4:
            open_entry = (ts, parts[3])
        elif marker == "o" and open_entry is not None:
            start, account = open_entry
            entries.append((start, ts, account))
            open_entry = None

    return entries
