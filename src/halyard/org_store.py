"""Org store — SQLite persistence for normalized OrgSession records.

The database lives at <hub>/org.db.  Contributors run `halyard sync` to push
normalized records from their local ai-sessions.log into this store.

Schema is append-only.  The local_log_line_hash column enforces idempotency:
re-syncing the same log line is a no-op.

FROZEN — ENTERPRISE EXTRACTION CANDIDATE. This module is scaffolding for
the planned ``halyard-enterprise`` package and is off-limits for new
feature work in OSS Halyard. Bug fixes affecting solo-user paths only.
See CONTRIBUTING.md.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from halyard.org import OrgSession

ORG_DB_FILENAME = "org.db"

_DDL = """
CREATE TABLE IF NOT EXISTS org_sessions (
    id                   INTEGER PRIMARY KEY,
    org_id               TEXT    NOT NULL,
    team_id              TEXT    NOT NULL,
    user_id              TEXT    NOT NULL,
    project_id           TEXT    NOT NULL DEFAULT '',
    attribution_state    TEXT    NOT NULL DEFAULT 'unattributed',
    tool                 TEXT    NOT NULL,
    model                TEXT    NOT NULL,
    source               TEXT    NOT NULL DEFAULT '',
    billing              TEXT    NOT NULL DEFAULT 'api',
    start_ts             TEXT    NOT NULL,
    end_ts               TEXT    NOT NULL,
    input_tokens         INTEGER NOT NULL DEFAULT 0,
    output_tokens        INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens    INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd             REAL    NOT NULL DEFAULT 0.0,
    allocated_usd        REAL    NOT NULL DEFAULT 0.0,
    trust                TEXT    NOT NULL DEFAULT 'missing',
    tags                 TEXT    NOT NULL DEFAULT '',
    local_log_line_hash  TEXT    NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_org_team
    ON org_sessions (org_id, team_id, start_ts);

CREATE INDEX IF NOT EXISTS idx_org_project
    ON org_sessions (org_id, project_id, start_ts);

CREATE INDEX IF NOT EXISTS idx_org_user
    ON org_sessions (org_id, user_id, start_ts);

CREATE TABLE IF NOT EXISTS sync_audit (
    id           INTEGER PRIMARY KEY,
    org_id       TEXT    NOT NULL,
    synced_by    TEXT    NOT NULL,
    synced_at    TEXT    NOT NULL,
    source_path  TEXT    NOT NULL DEFAULT '',
    inserted     INTEGER NOT NULL DEFAULT 0,
    skipped      INTEGER NOT NULL DEFAULT 0,
    event        TEXT    NOT NULL DEFAULT 'sync'
);
"""


@contextmanager
def _connect(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.executescript(_DDL)


def insert_session(db_path: Path, session: OrgSession) -> bool:
    """Insert a normalized session record.  Returns True if inserted, False if duplicate."""
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO org_sessions (
                    org_id, team_id, user_id, project_id, attribution_state,
                    tool, model, source, billing, start_ts, end_ts,
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                    cost_usd, allocated_usd, trust, tags, local_log_line_hash
                ) VALUES (
                    :org_id, :team_id, :user_id, :project_id, :attribution_state,
                    :tool, :model, :source, :billing, :start_ts, :end_ts,
                    :input_tokens, :output_tokens, :cache_read_tokens, :cache_write_tokens,
                    :cost_usd, :allocated_usd, :trust, :tags, :local_log_line_hash
                )
                """,
                {
                    "org_id": session.org_id,
                    "team_id": session.team_id,
                    "user_id": session.user_id,
                    "project_id": session.project_id,
                    "attribution_state": session.attribution_state,
                    "tool": session.tool,
                    "model": session.model,
                    "source": session.source,
                    "billing": session.billing,
                    "start_ts": session.start.isoformat(),
                    "end_ts": session.end.isoformat(),
                    "input_tokens": session.input_tokens,
                    "output_tokens": session.output_tokens,
                    "cache_read_tokens": session.cache_read_tokens,
                    "cache_write_tokens": session.cache_write_tokens,
                    "cost_usd": session.cost_usd,
                    "allocated_usd": session.allocated_usd,
                    "trust": session.trust,
                    "tags": " ".join(session.tags),
                    "local_log_line_hash": session.local_log_line_hash,
                },
            )
            return True
        except sqlite3.IntegrityError:
            return False


def insert_sessions(db_path: Path, sessions: list[OrgSession]) -> tuple[int, int]:
    """Bulk insert sessions.  Returns (inserted, skipped) counts."""
    inserted = skipped = 0
    for s in sessions:
        if insert_session(db_path, s):
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


# ---------------------------------------------------------------------------
# Sync audit log
# ---------------------------------------------------------------------------


def record_sync(
    db_path: Path,
    org_id: str,
    synced_by: str,
    inserted: int,
    skipped: int,
    source_path: str = "",
    event: str = "sync",
) -> None:
    """Append one immutable sync event to the audit log."""
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sync_audit
                (org_id, synced_by, synced_at, source_path, inserted, skipped, event)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [org_id, synced_by, datetime.now().isoformat(), source_path, inserted, skipped, event],
        )


def read_sync_audit(db_path: Path, org_id: str, limit: int = 50) -> list[dict]:  # type: ignore[type-arg]
    """Return recent sync audit events, newest first."""
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT synced_by, synced_at, source_path, inserted, skipped, event
            FROM sync_audit
            WHERE org_id = ?
            ORDER BY synced_at DESC
            LIMIT ?
            """,
            [org_id, limit],
        ).fetchall()
    return [dict(r) for r in rows]


def purge_user(db_path: Path, org_id: str, user_id: str, purged_by: str) -> int:
    """Delete all session records for a user and log the purge in the audit trail.

    Returns the number of records deleted.  The audit entry is always written
    even if the count is zero so the request is on record.
    """
    ensure_schema(db_path)
    with _connect(db_path) as conn:
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM org_sessions WHERE org_id = ? AND user_id = ?",
                [org_id, user_id],
            ).fetchone()[0]
        )
        conn.execute(
            "DELETE FROM org_sessions WHERE org_id = ? AND user_id = ?",
            [org_id, user_id],
        )
        conn.execute(
            """
            INSERT INTO sync_audit
                (org_id, synced_by, synced_at, source_path, inserted, skipped, event)
            VALUES (?, ?, ?, ?, 0, 0, ?)
            """,
            [org_id, purged_by, datetime.now().isoformat(), user_id, f"purge:{user_id}"],
        )
    return count


# ---------------------------------------------------------------------------
# Rollup queries
# ---------------------------------------------------------------------------


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def team_monthly_rollup(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
    team_id: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    """Return per-team cost and session summary for a billing month."""
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

    where = "org_id = ? AND start_ts >= ? AND start_ts < ?"
    params: list[object] = [org_id, period_start, period_end]
    if team_id:
        where += " AND team_id = ?"
        params.append(team_id)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                team_id,
                COUNT(*)                          AS sessions,
                COUNT(DISTINCT user_id)           AS active_users,
                SUM(cost_usd)                     AS direct_usd,
                SUM(allocated_usd)                AS allocated_usd,
                SUM(cost_usd + allocated_usd)     AS total_usd,
                SUM(input_tokens + output_tokens) AS total_tokens,
                SUM(CASE WHEN project_id = '' THEN 1 ELSE 0 END) AS unattributed
            FROM org_sessions
            WHERE {where}
            GROUP BY team_id
            ORDER BY total_usd DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def project_monthly_rollup(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
    project_id: str | None = None,
    team_id: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

    where = "org_id = ? AND start_ts >= ? AND start_ts < ? AND project_id != ''"
    params: list[object] = [org_id, period_start, period_end]
    if project_id:
        where += " AND project_id = ?"
        params.append(project_id)
    if team_id:
        where += " AND team_id = ?"
        params.append(team_id)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                project_id,
                team_id,
                COUNT(*)                          AS sessions,
                COUNT(DISTINCT user_id)           AS contributors,
                SUM(cost_usd)                     AS direct_usd,
                SUM(allocated_usd)                AS allocated_usd,
                SUM(cost_usd + allocated_usd)     AS total_usd,
                SUM(CASE WHEN attribution_state = 'inferred' THEN 1 ELSE 0 END) AS inferred_sessions
            FROM org_sessions
            WHERE {where}
            GROUP BY project_id, team_id
            ORDER BY total_usd DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def user_monthly_rollup(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
    team_id: str | None = None,
) -> list[dict]:  # type: ignore[type-arg]
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

    where = "org_id = ? AND start_ts >= ? AND start_ts < ?"
    params: list[object] = [org_id, period_start, period_end]
    if team_id:
        where += " AND team_id = ?"
        params.append(team_id)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                user_id,
                team_id,
                COUNT(*)                          AS sessions,
                COUNT(DISTINCT DATE(start_ts))    AS active_days,
                SUM(cost_usd + allocated_usd)     AS total_usd,
                GROUP_CONCAT(DISTINCT tool)       AS tools
            FROM org_sessions
            WHERE {where}
            GROUP BY user_id, team_id
            ORDER BY sessions DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def org_monthly_summary(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
) -> dict:  # type: ignore[type-arg]
    """Top-level org summary for the CIO view."""
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                          AS sessions,
                COUNT(DISTINCT user_id)           AS active_users,
                COUNT(DISTINCT team_id)           AS active_teams,
                SUM(cost_usd)                     AS direct_usd,
                SUM(allocated_usd)                AS allocated_usd,
                SUM(cost_usd + allocated_usd)     AS total_usd,
                SUM(input_tokens + output_tokens) AS total_tokens,
                SUM(CASE WHEN project_id = '' THEN 1 ELSE 0 END) AS unattributed
            FROM org_sessions
            WHERE org_id = ? AND start_ts >= ? AND start_ts < ?
            """,
            [org_id, period_start, period_end],
        ).fetchone()
        model_rows = conn.execute(
            """
            SELECT model, COUNT(*) AS sessions, SUM(cost_usd) AS direct_usd
            FROM org_sessions
            WHERE org_id = ? AND start_ts >= ? AND start_ts < ?
            GROUP BY model
            ORDER BY sessions DESC
            """,
            [org_id, period_start, period_end],
        ).fetchall()
        tool_rows = conn.execute(
            """
            SELECT tool, COUNT(*) AS sessions
            FROM org_sessions
            WHERE org_id = ? AND start_ts >= ? AND start_ts < ?
            GROUP BY tool
            ORDER BY sessions DESC
            """,
            [org_id, period_start, period_end],
        ).fetchall()

    return {
        **(dict(row) if row else {}),
        "model_mix": [dict(r) for r in model_rows],
        "tool_mix": [dict(r) for r in tool_rows],
    }


def governance_gaps(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
    unattributed_threshold: float = 0.10,
) -> dict:  # type: ignore[type-arg]
    """Return governance health data: unattributed rates, missing-cost sessions."""
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

    with _connect(db_path) as conn:
        team_rows = conn.execute(
            """
            SELECT
                team_id,
                COUNT(*) AS total,
                SUM(CASE WHEN project_id = '' THEN 1 ELSE 0 END) AS unattributed,
                SUM(CASE WHEN trust = 'missing' THEN 1 ELSE 0 END) AS missing_cost
            FROM org_sessions
            WHERE org_id = ? AND start_ts >= ? AND start_ts < ?
            GROUP BY team_id
            """,
            [org_id, period_start, period_end],
        ).fetchall()

    alerts = []
    for r in team_rows:
        rate = r["unattributed"] / r["total"] if r["total"] else 0.0
        if rate > unattributed_threshold:
            alerts.append(
                {
                    "team_id": r["team_id"],
                    "type": "unattributed_rate",
                    "rate": round(rate, 3),
                    "unattributed": r["unattributed"],
                    "total": r["total"],
                }
            )
        if r["missing_cost"] > 0:
            alerts.append(
                {
                    "team_id": r["team_id"],
                    "type": "missing_cost",
                    "count": r["missing_cost"],
                }
            )

    return {"alerts": alerts, "teams": [dict(r) for r in team_rows]}


def finance_export(
    db_path: Path,
    org_id: str,
    year: int,
    month: int,
) -> list[dict]:  # type: ignore[type-arg]
    """Rows for the finance cost-center export CSV."""
    period_start = f"{year:04d}-{month:02d}-01"
    period_end = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                team_id,
                project_id,
                tool,
                COUNT(*)                      AS sessions,
                SUM(cost_usd)                 AS direct_usd,
                SUM(allocated_usd)            AS allocated_usd,
                SUM(cost_usd + allocated_usd) AS total_usd,
                CASE
                    WHEN SUM(cost_usd) > 0 AND SUM(allocated_usd) > 0 THEN 'mixed'
                    WHEN SUM(allocated_usd) > 0 THEN 'allocated'
                    WHEN SUM(cost_usd) > 0 THEN 'captured'
                    ELSE 'missing'
                END AS trust
            FROM org_sessions
            WHERE org_id = ? AND start_ts >= ? AND start_ts < ?
            GROUP BY team_id, project_id, tool
            ORDER BY team_id, project_id, tool
            """,
            [org_id, period_start, period_end],
        ).fetchall()

    billing_period = f"{year:04d}-{month:02d}"
    return [{"billing_period": billing_period, "org_id": org_id, **dict(r)} for r in rows]
