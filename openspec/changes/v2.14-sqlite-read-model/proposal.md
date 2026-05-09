# Proposal: v2.14 — SQLite Read Model

## Why

Halyard's plain-text log files are the right source of truth: human-readable,
git-friendly, and zero-dependency. But they become slow to query as they grow,
and the ad-hoc parsing spread across `ai_log.py`, `reports.py`, and
`ledger.py` makes it hard to answer cross-file questions like "total cost
across all projects this quarter" without loading everything into memory.

A derived SQLite cache solves both problems: fast structured queries without
replacing the plain-text files as the canonical record.

## What changes

- `halyard db sync` command builds or refreshes a SQLite database at
  `~/.halyard/cache.db` from all known project and hub log files.
- The database is a read cache only — it is never the source of truth.
- The log agent (`halyard log`) gains a `--db` flag to query the SQLite cache
  instead of the AI log agent, enabling SQL-level queries without an LLM.
- The dashboard can optionally use the cache for faster page renders on large
  logs (transparent, no user-visible change).

## What stays the same

- Plain-text files remain the source of truth.
- All writes go to the text files, never directly to SQLite.
- `halyard db sync` is idempotent and safe to re-run.
- No always-on background sync process; users run `sync` when they want the
  cache refreshed, or hook it into their workflow.

## Out of scope

- Real-time / automatic sync.
- SQLite as a write path.
- Multi-user or networked database.
- Replacing the log agent with SQL for natural-language queries.

## Success criteria

- `halyard db sync` runs without error on a real project.
- `halyard db sync --status` shows last-sync time and row counts.
- The SQLite schema matches the session and timeclock data models.
- Querying the cache with a standard SQLite client returns correct session rows.

## v2.18 amendments

v2.18 (Cache and Audit Hardening) extends this design in three ways:

1. **Project registry** — `halyard db sync` no longer relies solely on CWD
   discovery. It reads `~/.halyard/projects` (one absolute path per line) as its
   primary source. `halyard init` registers the project automatically.

2. **Schema migrations** — `cache.db` now carries `PRAGMA user_version`. Every
   schema change ships a forward migration in `_MIGRATIONS`. Destructive changes
   use the `REQUIRES_RESET` sentinel and prompt the user to run
   `halyard db reset && halyard db sync` rather than silently dropping data.

3. **Content-addressed session ID** — The session primary key is now
   `sha256(start|end|tool|model|input_tok|output_tok)` instead of
   `sha256(raw_line)`. This makes the ID stable across amendment records: an
   `a <hash> project=...` attribution correction does not create a second row.
   The `REQUIRES_RESET` migration path handles the transition from old IDs.
