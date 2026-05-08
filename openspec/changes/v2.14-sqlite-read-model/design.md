# Design

## Database location

`~/.halyard/cache.db` — global cache, covers all projects and the hub.

Individual project-scoped cache at `<project>/.halyard-cache/halyard.db` is
out of scope for v2.14 but should not be precluded by schema choices.

## Schema

```sql
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,   -- sha256 of raw log line
    project     TEXT,
    tool        TEXT NOT NULL,
    model       TEXT NOT NULL,
    started_at  TEXT NOT NULL,      -- ISO 8601
    ended_at    TEXT NOT NULL,
    input_tok   INTEGER NOT NULL DEFAULT 0,
    output_tok  INTEGER NOT NULL DEFAULT 0,
    cache_read  INTEGER,
    cache_write INTEGER,
    cost_usd    REAL NOT NULL DEFAULT 0,
    tool_calls  INTEGER,
    tool_errors INTEGER,
    source_file TEXT NOT NULL       -- absolute path to log file
);

CREATE TABLE timeclock (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project     TEXT NOT NULL,      -- "client:project" slug
    started_at  TEXT NOT NULL,
    ended_at    TEXT,               -- NULL if open entry
    source_file TEXT NOT NULL
);

CREATE TABLE sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    synced_at   TEXT NOT NULL,
    files_read  INTEGER NOT NULL,
    rows_added  INTEGER NOT NULL
);
```

## `halyard db sync` command

1. Discovers all project dirs and the hub via the same logic as `find_project_dir` / `find_hub`.
2. Parses each `ai-sessions.log` and `time.timeclock`.
3. Upserts rows into `sessions` and `timeclock` (keyed by `id` / unique index on source_file+started_at).
4. Writes a row to `sync_log`.
5. Prints: `Synced N sessions across M files.`

`--status` flag prints last sync time and counts without re-syncing.

## Module

`src/halyard/db.py` — new module.

Key functions:
- `sync_all() -> SyncResult`
- `get_db() -> sqlite3.Connection`
- `db_path() -> Path`

## Dashboard integration

`render_dashboard` can optionally call `get_db()` instead of `parse_sessions`
when `cache.db` exists and is less than 60 seconds old. This is a transparent
optimization with no user-visible change. Implement only if benchmarks show
meaningful improvement on large logs (>10k sessions).
