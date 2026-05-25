# Design — v5.9 Review remediation

Targeted correctness fixes from the post-v5.8 review. Each is minimal and
local; no format/contract change; the append-only log is still never rewritten.

## #1 Windows read-lock crash (HIGH)
`read_locked_file` released a lock it never took on Windows. Add a symmetric
`_release_read_lock` per platform branch (win32 no-op, posix-fcntl `LOCK_UN`,
no-fcntl no-op) and call it from `read_locked_file`'s `finally` instead of the
writer's `_release_lock`. POSIX behaviour identical (`LOCK_UN` releases a
`LOCK_SH`); Windows no longer raises `OSError` out of `parse_sessions`.

## #8 Read/write contention
`parse_sessions` now reads all lines into a list under the shared lock, then
releases before parsing + quarantine writes. Torn-read safety preserved (the
file read still happens under the lock); the Hub's exclusive append is no longer
blocked for the whole parse. Memory is unchanged in practice (all sessions were
already materialized into a list).

## #4 / #6 attribution
- `canonical_project` resolves alias chains (`A→B→C`) with a `seen` cycle guard.
- `load_project_aliases` caches `(path, mtime, dict)`; a write (which bumps
  mtime) invalidates it. Removes the per-`parse_sessions` TOML re-parse.

## #5 budget / invoice canonicalization
Both `budget.budget_status` and `invoicing._ai_cost_for` / the evidence appendix
canonicalize the config-side slug/accounts (`canonical_project`) before matching
against the already-canonical `session.project`, so a budget/invoice keyed on an
aliased raw slug still matches.

## #3 Hub write resilience
`_process_write_queue` wraps each `_write_to_log` in its own `try/except` +
`log_diagnostic`, so one failing write can't drop the rest of the drained batch
(the v5.5 worker-level guard alone would have silently lost them).

## #9 Live slug consistency
The `collision_detected` event canonicalizes `session.project` so the live
banner matches the canonical slug shown by the persistent panels.

## #2 / #7 dashboard
- The "reset layout" handler also `removeItem`s `halyard-removed-v1`, so reset
  restores hidden panels (browser-verified).
- `_overview_panels` outcomes count unique `pr_ref` (one merged PR with N
  sessions counts once); sessions without a PR are counted individually; the
  dead `"draft"` branch is removed.

## Tests
`test_v59_review_remediation.py`: transitive/cycle canonicalization; alias cache
refresh; read path uses `_release_read_lock`; per-item write resilience; budget
matches an aliased slug. #2 browser-verified; #7/#8/#9 covered by the full suite.
