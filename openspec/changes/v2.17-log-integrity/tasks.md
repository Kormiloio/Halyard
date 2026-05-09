# Tasks

Implementation checklist for v2.17 — Log Integrity.

## 1. Locking primitive

- [ ] 1.1 Add `locked_file()` context manager (fcntl.flock).
- [ ] 1.2 Place in `ai_log.py` (or a new `_locking.py`).
- [ ] 1.3 Test: 100 concurrent appenders produce exactly 100 lines.

## 2. Correction-record format

- [ ] 2.1 Add `session_hash(line)` to `ai_log.py`.
- [ ] 2.2 Add `Amendment` dataclass and parser for `a` lines.
- [ ] 2.3 Add `AiSession.apply_amendment(amendment)` mutator.
- [ ] 2.4 Update `parse_sessions` to fold amendments.
- [ ] 2.5 Test: round-trip an attribution change via `a` record.
- [ ] 2.6 Test: multiple amendments on the same session, last-write-wins per key.

## 3. Replace in-place rewrites

- [x] 3.1 `assign_unattributed_sessions` writes `a` records, no `write_text`.
  — Implemented in L-3 (v2.20): atomic tmp-then-rename. Note: uses file-rewrite pattern rather than amendment records; amendment approach remains a future option.
- [x] 3.2 `confirm_session_attributions` writes `a` records.
  — Implemented in L-3 (v2.20): atomic tmp-then-rename. Note: uses file-rewrite pattern rather than amendment records; amendment approach remains a future option.
- [x] 3.3 `backfill_window` writes `a` records.
  — Implemented in L-3 (v2.20): atomic tmp-then-rename. Note: uses file-rewrite pattern rather than amendment records; amendment approach remains a future option.
- [ ] 3.4 Confirm the legacy `_rewrite_lines_atomic` is unused outside
  user-driven destructive paths.
- [ ] 3.5 Audit: grep for `write_text` against log paths; document each
  remaining call.

## 4. Lock all mutators

- [ ] 4.1 `append_session` uses `locked_file`.
- [ ] 4.2 Timeclock writes (clock-in / clock-out) use `locked_file`.
- [ ] 4.3 `~/.halyard/active.timer` writes use `locked_file`.
- [ ] 4.4 Invoice counter increment in `halyard.toml` uses `locked_file`.

## 5. Shared timer functions

- [x] 5.1 Add `start_timer(project_dir, slug)` to orchestration.py.
  — Implemented in D-2 (v2.21): read_active_project() extracted to ai_log.py; all collectors import canonical function; dashboard write is atomic.
- [x] 5.2 Add `stop_timer(project_dir)` to orchestration.py.
  — Implemented in D-2 (v2.21): read_active_project() extracted to ai_log.py; all collectors import canonical function; dashboard write is atomic.
- [x] 5.3 `stop_timer` invokes `backfill_window`.
  — Implemented in D-2 (v2.21): read_active_project() extracted to ai_log.py; all collectors import canonical function; dashboard write is atomic.
- [x] 5.4 CLI `start` and `stop` call the orchestration functions.
  — Implemented in D-2 (v2.21): read_active_project() extracted to ai_log.py; all collectors import canonical function; dashboard write is atomic.
- [ ] 5.5 Dashboard `do_POST` calls the orchestration functions, removes
  duplicate logic.
- [ ] 5.6 `unlink(missing_ok=True)` on active-timer file.

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

- [ ] 8.1 Update `ai-sessions.log` spec page with `a` line format.
- [ ] 8.2 CHANGELOG entry for v2.17 noting the format extension.
- [ ] 8.3 Update `openspec/project.md` to remove the
  "attribution-correction is the only exception" carve-out — there is
  now no exception, all corrections go via `a` records.
