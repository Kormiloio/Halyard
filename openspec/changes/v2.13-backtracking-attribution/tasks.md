# Tasks

Implementation checklist for v2.13 — Backtracking Attribution.

## 1. Core function

- [ ] 1.1 Add `backfill_window(project_dir, start, end, project, *, dry_run)` to `ai_log.py`.
- [ ] 1.2 Add `_last_closed_window(timeclock_path, account)` helper.
- [ ] 1.3 Write unit tests for `backfill_window` (match, no-match, dry-run, already-attributed).

## 2. Auto-attribution on stop

- [ ] 2.1 Call `backfill_window` in `halyard stop` after the `o` line is written.
- [ ] 2.2 Print attributed count when > 0.
- [ ] 2.3 No output when 0 sessions matched.

## 3. `halyard backfill` command

- [ ] 3.1 Add `halyard backfill` command to `cli.py`.
- [ ] 3.2 Implement `--dry-run` mode.
- [ ] 3.3 Implement `--project` filter.
- [ ] 3.4 Implement `--confirm` interactive mode for ambiguous sessions.
- [ ] 3.5 Print summary: attributed / skipped-ambiguous / skipped-no-window.

## 4. Tests

- [ ] 4.1 Test stop auto-attribution with matching sessions in window.
- [ ] 4.2 Test stop auto-attribution with no sessions in window (no output).
- [ ] 4.3 Test `halyard backfill --dry-run` reports but does not write.
- [ ] 4.4 Test overlap/ambiguity skipping.
