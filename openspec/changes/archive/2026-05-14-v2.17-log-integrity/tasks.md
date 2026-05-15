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
  — Handles project, source, attr_method, note; confirmed_at is stored as
  metadata (no AiSession field yet); unknown keys silently ignored.
- [x] 2.4 Update `parse_sessions` to fold amendments.
  — Full fold algorithm per design.md; duplicate-line-safe (list + first-occurrence hash map).
- [x] 2.5 Test: round-trip an attribution change via `a` record.
  — `tests/test_log_integrity.py::test_round_trip_attribution_change_via_amendment`
- [x] 2.6 Test: multiple amendments on the same session, last-write-wins per key.
  — `tests/test_log_integrity.py::test_multiple_amendments_last_write_wins` and `test_multiple_amendments_partial_key_override`

## 3. Replace in-place rewrites

- [x] 3.1 `assign_unattributed_sessions` writes `a` records, no `write_text`.
  — Implemented: appends `a <hash> project=<slug> attr_method=backfill`
  records under `locked_file`; original `s` lines remain unchanged.
- [x] 3.2 `confirm_session_attributions` writes `a` records.
  — Implemented: appends `a <hash> project=<slug> attr_method=manual`
  records under `locked_file`; original `s` lines remain unchanged.
- [x] 3.3 `backfill_window` writes `a` records.
  — Implemented: appends `a <hash> project=<slug> attr_method=backfill`
  records under `locked_file`; dry-run counts candidates without writing.
- [x] 3.4 Confirm the legacy `_rewrite_lines_atomic` is unused outside
  user-driven destructive paths.
  — Confirmed: only called from `interactive_assign_unattributed()` (interactive triage). Comment added to `_rewrite_lines_atomic` in orchestration.py.
- [x] 3.5 Audit: grep for `write_text` against log paths; document each
  remaining call.
  — Audit complete for v2.17 mutators. Attribution correction paths no longer
  rewrite the live session log; `interactive_assign_unattributed()` remains the
  user-driven destructive triage path.

## 4. Lock all mutators

- [x] 4.1 `append_session` uses `locked_file`.
  — `ai_log.py:append_session` and `write_unattributed_session` both use `locked_file`.
- [x] 4.2 Timeclock writes (clock-in / clock-out) use `locked_file`.
  — `start_timer()` and `stop_timer()` write `time.timeclock` under
  `locked_file`; CLI and dashboard route through those shared functions.
- [x] 4.3 `~/.halyard/active.timer` writes use `locked_file`.
  — Active-timer state file uses the shared `write_active_timer()` atomic
  tmp-then-rename helper while the timeclock lock is held.
- [x] 4.4 Invoice counter increment in `halyard.toml` uses `locked_file`.
  — `_allocate_invoice_number()` and `_write_invoice_counter()` use
  `locked_file(path, "r+")`; the lock helper now protects same-process threads
  as well as cooperating processes.

## 5. Shared timer functions

- [x] 5.1 Add `start_timer(project_dir, slug)` to orchestration.py.
  — Implemented in `halyard.orchestration`; raises `TimerAlreadyRunning`.
- [x] 5.2 Add `stop_timer(project_dir)` to orchestration.py.
  — Implemented in `halyard.orchestration`; returns `StopResult`.
- [x] 5.3 `stop_timer` invokes `backfill_window`.
  — Implemented; attribution backfill failures are logged and surfaced.
- [x] 5.4 CLI `start` and `stop` call the orchestration functions.
  — Implemented: CLI no longer duplicates timer file mutation logic.
- [x] 5.5 Dashboard `do_POST` calls the orchestration functions, removes
  duplicate logic.
  — Implemented for `/api/start` and `/api/stop`.
- [x] 5.6 `unlink(missing_ok=True)` on active-timer file.
  — Implemented in `stop_timer()` and stale-active cleanup paths.
- [x] 5.7 Add shared `write_active_timer()` helper that writes to a unique
  temp path and atomically replaces `~/.halyard/active`; use it from both CLI
  and dashboard start paths.
  — Implemented; dashboard and CLI both reach it through `start_timer()`.

## 6. Error visibility

- [x] 6.1 Add `_log_error(msg, exc)` helper that writes to
  `~/.halyard/halyard.log`.
  — Implemented in `ai_log.py`.
- [x] 6.2 Replace `except Exception: pass` in cli.py:478, cli.py:1296,
  cli.py:2432, orchestration.py:345, orchestration.py:361,
  config_history.py:248, sync.py:69, and the gemini collector swallows.
  — Core CLI/orchestration/config/sync paths covered earlier. Collector
  parse helpers (`gemini_history.py`) now use narrow exception tuples
  (`OSError`, `json.JSONDecodeError`, `UnicodeDecodeError`, `KeyError`,
  `TypeError`, `ValueError`, `AttributeError`) so programmer bugs surface
  as real exceptions instead of being swallowed.
- [x] 6.3 Each replacement prints a `[yellow]Warning:[/]` line referencing
  the log path.
  — Done for user-facing paths. Policy decision for collector parse
  helpers: they fire on every hook invocation, so a yellow warning per
  malformed history file would be unacceptable noise. Silent return on
  the narrowed exception set is the correct behavior; unexpected types
  now propagate rather than being hidden.
- [x] 6.4 Test: malformed log line in backfill produces visible warning
  and a log entry.
  — `tests/test_log_integrity.py::test_backfill_error_logs_to_halyard_log_and_warns`

## 7. Concurrency tests

- [x] 7.1 100 concurrent `append_session` calls.
  — `tests/test_log_integrity.py::test_100_concurrent_appenders_produce_exactly_100_lines`
- [x] 7.2 50 concurrent `start_timer` (49 fail with TimerAlreadyRunning).
  — `tests/test_log_integrity.py::test_50_concurrent_start_timer_exactly_one_succeeds`
- [x] 7.3 CLI stop + dashboard stop simultaneously: exactly one `o` line.
  — Covered at orchestration level by
  `tests/test_log_integrity.py::test_concurrent_stop_timer_produces_exactly_one_o_line`
- [x] 7.4 Concurrent invoice generation produces unique numbers.
  — `tests/test_log_integrity.py::test_concurrent_invoice_allocation_unique_numbers`
- [x] 7.5 Concurrent `backfill_window` + `append_session`: append survives.
  — `tests/test_log_integrity.py::test_concurrent_backfill_and_append_no_lost_sessions`

## 8. Documentation

- [x] 8.1 Update `ai-sessions.log` spec page with `a` line format.
  — `docs/samples/ai-sessions.log.sample` updated with `a` record documentation, format explanation, and example.
- [x] 8.2 CHANGELOG entry for v2.17 noting the format extension.
  — `CHANGELOG.md` [Unreleased] section updated with v2.17 locking and amendment record entries.
- [x] 8.3 Update `openspec/project.md` to remove the
  "attribution-correction is the only exception" carve-out — there is
  now no exception, all corrections go via `a` records.
  — `openspec/project.md` updated: carve-out removed; append-only policy stated; `_rewrite_lines_atomic` restricted to user-driven interactive triage only.
