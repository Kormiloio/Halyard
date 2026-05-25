# v5.9 — Review remediation (correctness pass)

## Why

A correctness review of this session's work (v5.3–v5.8) surfaced one
Windows-breaking regression plus several real correctness/consistency bugs.
This fixes them.

## What changes

1. **[HIGH] Windows read-lock crash.** `read_locked_file` (v5.3) released a lock
   it never acquired on Windows (`_acquire_read_lock` is a no-op there, but the
   `finally` called the writer's `LK_UNLCK`), raising `OSError` out of every
   `parse_sessions`. Add a symmetric `_release_read_lock` (no-op on Windows,
   `LOCK_UN` on POSIX).
2. **Reset layout restores hidden panels.** The reset handler now also clears
   `halyard-removed-v1` (per-panel hide state), not just order + collapse.
3. **No silent batch loss.** `_process_write_queue` writes each session in its
   own `try/except` (log + continue) so one failing write no longer drops the
   rest of the drained batch.
4. **Transitive alias resolution.** `canonical_project` follows alias chains
   (`A→B→C`) with a cycle guard, so chained aliases no longer split a project.
5. **Budget/invoice configs canonicalized.** Budget and invoice project-account
   matching canonicalizes the config slug before comparing to the (now
   canonical) `session.project`, so a budget/invoice keyed on an aliased raw
   slug still matches.
6. **Alias map cached.** `load_project_aliases` caches by file mtime instead of
   re-reading + re-parsing the TOML on every `parse_sessions`.
7. **Overview "Outcomes" counts PRs, not sessions.** Dedupe by `pr_ref` so one
   merged PR with N sessions counts once; drop the dead `"draft"` branch.
8. **Lower read/write contention.** `parse_sessions` reads the log lines under
   the shared lock, then releases before parsing/quarantine work — torn-read
   safety preserved, but the Hub's append is no longer blocked for the whole
   parse.
9. **Consistent live slug.** The Hub's live `/state` + `collision_detected`
   project slug is canonicalized so the live banner matches the persistent
   panels after aliasing.

## Impact

- Affected: `ai_log.py`, `attribution.py`, `budget.py`, `invoicing.py`,
  `hub_server.py`, `dashboard.py`. Tests added per fix.
- No format/contract changes; the append-only log is still never rewritten.
