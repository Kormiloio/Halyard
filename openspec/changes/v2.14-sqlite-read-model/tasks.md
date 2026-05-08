# Tasks

Implementation checklist for v2.14 — SQLite Read Model.

## 1. Module and schema

- [x] 1.1 Create `src/halyard/db.py`.
- [x] 1.2 Implement `db_path() -> Path` returning `~/.halyard/cache.db`.
- [x] 1.3 Implement `get_db() -> sqlite3.Connection` with schema migration.
- [x] 1.4 Create `sessions`, `timeclock`, and `sync_log` tables on first open.

## 2. Sync logic

- [x] 2.1 Implement `sync_all() -> SyncResult` discovering all project dirs and hub.
- [x] 2.2 Parse each `ai-sessions.log` and upsert into `sessions`.
- [x] 2.3 Parse each `time.timeclock` and upsert into `timeclock`.
- [x] 2.4 Write `sync_log` row with timestamp and counts.

## 3. CLI command

- [x] 3.1 Add `halyard db sync` command.
- [x] 3.2 Add `halyard db sync --status` flag (print last sync without re-syncing).
- [x] 3.3 Add `halyard db reset` command (delete `cache.db`).

## 4. Tests

- [x] 4.1 Test `sync_all` against a fixture project dir.
- [x] 4.2 Test idempotency (second sync does not duplicate rows).
- [x] 4.3 Test `--status` output when cache exists vs. does not exist.

## 5. Optional dashboard optimization

- [ ] 5.1 Benchmark `parse_sessions` vs. SQLite query on 10k+ session log.
- [ ] 5.2 Add optional fast path in `render_dashboard` if benchmark warrants it.
