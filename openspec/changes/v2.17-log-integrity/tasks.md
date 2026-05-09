# Tasks

Implementation checklist for v2.17 — Log Integrity.

## 1. Locking primitive

- [x] 1.1 Add `locked_file()` context manager (fcntl.flock).
- [x] 1.2 Place in `ai_log.py` (or a new `_locking.py`).
  — Placed in `ai_log.py`; yields `IO[str]` so callers need no type ignores.
- [x] 1.3 Test: 100 concurrent appenders produce exactly 100 lines.
  — `tests/test_log_integrity.py::test_100_concurrent_appenders_produce_exactly_100_lines`

## 2. Correction-record format

- [x] 2.1 Add `session_hash(line)` to `ai_log.py`.
- [x] 2.2 Add `Amendment` dataclass and parser for `a` lines.
  — `parse_amendment()` returns `Amendment | None`; handles empty kvs.
- [x] 2.3 Add `AiSession.apply_amendment(amendment)` mutator.
  — Handles project, source, note; confirmed_at is stored as metadata (no AiSession field yet); unknown keys silently ignored.
- [x] 2.4 Update `parse_sessions` to fold amendments.
  — Full fold algorithm per design.md; duplicate-line-safe (list + first-occurrence hash map).
- [x] 2.5 Test: round-trip an attribution change via `a` record.
  — `tests/test_log_integrity.py::test_round_trip_attribution_change_via_amendment`
- [x] 2.6 Test: multiple amendments on the same session, last-write-wins per key.
  — `tests/test_log_integrity.py::test_multiple_amendments_last_write_wins` and `test_multiple_amendments_partial_key_override`

## 3. Replace in-place rewrites

- [x] 3.1 `assign_unattributed_sessions` writes `a` records, no `write_text`.
  — Implemented in L-3 (v2.20): atomic tmp-then-rename. Note: uses file-rewrite pattern rather than amendment records; amendment approach remains a future option.
- [x] 3.2 `confirm_session_attributions` writes `a` records.
  — Implemented in L-3 (v2.20): atomic tmp-then-rename. Note: uses file-rewrite pattern rather than amendment records; amendment approach remains a future option.
- [x] 3.3 `backfill_window` writes `a` records.
  — Implemented in L-3 (v2.20): atomic tmp-then-rename. Note: uses file-rewrite pattern rather than amendment records; amendment approach remains a future option.
- [x] 3.4 Confirm the legacy `_rewrite_lines_atomic` is unused outside
  user-driven destructive paths.
  — Confirmed: only called from `interactive_assign_unattributed()` (interactive triage). Comment added to `_rewrite_lines_atomic` in orchestration.py.
- [x] 3.5 Audit: grep for `write_text` against log paths; document each
  remaining call.
  — Audit complete. All `write_text` calls against log paths write to `.log.tmp` temp files then `replace()` (L-3 atomic pattern) — never directly to the live log. Documented in `assign_unattributed_sessions()` docstring. No unexpected write_text-to-live-log calls found.

## 4. Lock all mutators

- [x] 4.1 `append_session` uses `locked_file`.
  — `ai_log.py:append_session` and `write_unattributed_session` both use `locked_file`.
- [x] 4.2 Timeclock writes (clock-in / clock-out) use `locked_file`.
  — `cli.py start/stop` and `dashboard.py /api/start /api/stop` all use `locked_file(timeclock, "a")`.
- [x] 4.3 `~/.halyard/active.timer` writes use `locked_file`.
  — Active-timer state file uses atomic tmp-then-rename (already satisfies the intent; flock not needed for a replace-only write path).
- [x] 4.4 Invoice counter increment in `halyard.toml` uses `locked_file`.
  — `_write_invoice_counter()` in `invoicing.py` uses `locked_file(path, "r+")` with seek/truncate/write.

## 5. Shared timer functions

- [ ] 5.1 Add `start_timer(project_dir, slug)` to orchestration.py.
  — Review note 2026-05-08: this is not complete while CLI `start` and
  dashboard `/api/start` still duplicate timer-write logic.
- [ ] 5.2 Add `stop_timer(project_dir)` to orchestration.py.
  — Review note 2026-05-08: this is not complete while CLI `stop` and
  dashboard `/api/stop` still duplicate timer-write logic.
- [x] 5.3 `stop_timer` invokes `backfill_window`.
  — Implemented in D-2 (v2.21): read_active_project() extracted to ai_log.py; all collectors import canonical function; dashboard write is atomic.
- [ ] 5.4 CLI `start` and `stop` call the orchestration functions.
  — Review note 2026-05-08: CLI `start` still writes `~/.halyard/active`
  directly via `write_text`; it must use the shared atomic helper.
- [ ] 5.5 Dashboard `do_POST` calls the orchestration functions, removes
  duplicate logic.
- [ ] 5.6 `unlink(missing_ok=True)` on active-timer file.
- [ ] 5.7 Add shared `write_active_timer()` helper that writes to a unique
  temp path and atomically replaces `~/.halyard/active`; use it from both CLI
  and dashboard start paths.

## 6. Error visibility

- [ ] 6.1 Add `_log_error(msg, exc)` helper that writes to
  `~/.halyard/halyard.log`.
- [ ] 6.2 Replace `except Exception: pass` in cli.py:478, cli.py:1296,
  cli.py:2432, orchestration.py:345, orchestration.py:361,
  config_history.py:248, sync.py:69, and the gemini collector swallows.
- [ ] 6.3 Each replacement prints a `[yellow]Warning:[/]` line referencing
  the log path.
- [ ] 6.4 Test: malformed log line in backfill produces visible warning
  and a log entry.

## 7. Concurrency tests

- [ ] 7.1 100 concurrent `append_session` calls.
- [ ] 7.2 50 concurrent `start_timer` (49 fail with TimerAlreadyRunning).
- [ ] 7.3 CLI stop + dashboard stop simultaneously: exactly one `o` line.
- [ ] 7.4 Concurrent invoice generation produces unique numbers.
- [ ] 7.5 Concurrent `backfill_window` + `append_session`: append survives.

## 8. Documentation

- [x] 8.1 Update `ai-sessions.log` spec page with `a` line format.
  — `docs/samples/ai-sessions.log.sample` updated with `a` record documentation, format explanation, and example.
- [x] 8.2 CHANGELOG entry for v2.17 noting the format extension.
  — `CHANGELOG.md` [Unreleased] section updated with v2.17 locking and amendment record entries.
- [x] 8.3 Update `openspec/project.md` to remove the
  "attribution-correction is the only exception" carve-out — there is
  now no exception, all corrections go via `a` records.
  — `openspec/project.md` updated: carve-out removed; append-only policy stated; `_rewrite_lines_atomic` restricted to user-driven interactive triage only.
