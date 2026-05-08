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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    project     TEXT,
    tool        TEXT NOT NULL,
    model       TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT NOT NULL,
    input_tok   INTEGER NOT NULL DEFAULT 0,
    output_tok  INTEGER NOT NULL DEFAULT 0,
    cache_read  INTEGER,
    cache_write INTEGER,
    cost_usd    REAL NOT NULL DEFAULT 0,
    tool_calls  INTEGER,
    tool_errors INTEGER,
    source_file TEXT NOT NULL
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
"""


@dataclass
class SyncResult:
    sessions_added: int
    timeclock_added: int
    files_read: int
    synced_at: datetime


def db_path() -> Path:
    return _DB_PATH


def get_db() -> sqlite3.Connection:
    """Open (and initialize if needed) the cache database."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def sync_all() -> SyncResult:
    """Sync all known project and hub log files into the cache."""
    from halyard.ai_log import AI_LOG_FILENAME, find_project_dir
    from halyard.hub import find_hub

    sources: set[Path] = set()
    project_dir = find_project_dir()
    if project_dir:
        sources.add(project_dir)
    hub_dir = find_hub()
    if hub_dir:
        sources.add(hub_dir)

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


def _session_id(raw_line: str) -> str:
    return hashlib.sha256(raw_line.strip().encode()).hexdigest()


def _sync_sessions(conn: sqlite3.Connection, log_path: Path) -> int:
    from halyard.ai_log import _parse_line

    added = 0
    source = str(log_path.resolve())

    for raw_line in log_path.read_text().splitlines():
        line = raw_line.strip()
        if not line.startswith("s "):
            continue
        session = _parse_line(line)
        if session is None:
            continue

        result = conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (id, project, tool, model, started_at, ended_at,
                 input_tok, output_tok, cache_read, cache_write,
                 cost_usd, tool_calls, tool_errors, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _session_id(line),
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
            ),
        )
        added += result.rowcount

    return added


def _sync_timeclock(conn: sqlite3.Connection, tc_path: Path) -> int:
    """Sync only closed timeclock entries (open entries are excluded)."""
    added = 0
    source = str(tc_path.resolve())

    for start, end, account in _parse_closed_timeclock(tc_path):
        result = conn.execute(
            """
            INSERT OR REPLACE INTO timeclock
                (project, started_at, ended_at, source_file)
            VALUES (?, ?, ?, ?)
            """,
            (account, start.isoformat(), end.isoformat(), source),
        )
        added += result.rowcount

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
