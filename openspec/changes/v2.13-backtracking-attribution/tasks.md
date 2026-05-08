# Tasks

Implementation checklist for v2.13 — Backtracking Attribution.

## 1. Core function

- [x] 1.1 Add `backfill_window(project_dir, start, end, project, *, dry_run)` to `ai_log.py`.
- [x] 1.2 `_last_closed_window` not needed — `stop` uses `active.started` from active state file directly.
- [x] 1.3 Write unit tests for `backfill_window` (match, no-match, dry-run, already-attributed, boundaries).

## 2. Auto-attribution on stop

- [x] 2.1 Call `backfill_window` in `halyard stop` after the `o` line is written.
- [x] 2.2 Print attributed count when > 0.
- [x] 2.3 No output when 0 sessions matched.

## 3. `halyard backfill` command

- [x] 3.1 Add `halyard backfill` command to `cli.py`.
- [x] 3.2 Implement `--dry-run` mode.
- [x] 3.3 Implement `--project` filter.
- [x] 3.4 Implement `--confirm` interactive mode for ambiguous sessions.
- [x] 3.5 Print summary: attributed / skipped-ambiguous / skipped-no-window.

## 4. Tests

- [x] 4.1 Test stop auto-attribution with matching sessions in window.
- [x] 4.2 Test stop auto-attribution with no sessions in window (no output).
- [x] 4.3 Test `halyard backfill --dry-run` reports but does not write.
- [x] 4.4 Test overlap/ambiguity skipping.
