# v5.3 — Concurrency + observability hardening

## Why

A due-diligence-style architecture review of Halyard raised five concerns.
After verifying each against the source, three were real and proportionate and
are addressed here (the other two — the dashboard f-string monolith and an
undocumented timezone model — ship as v5.4). The review also overstated some of
these; the scope below is the *verified* defect, not the headline.

1. **Readers took no lock.** Writers append under an exclusive `flock`
   (`locked_file`), but `parse_sessions` / `unattributed_log_count` read with a
   bare `open()`. A reader concurrent with an in-progress append of a large
   (>8 KB, multi-flush) line can observe a torn final line. The review claimed
   this "permanently quarantines valid data" — that part is false: a torn read
   only appends a *copy* to `quarantine.log`; the append-only ledger keeps the
   complete line and the next parse reads it correctly. So this is a
   cosmetic/robustness fix, not a data-loss fix — but worth closing.
2. **Silent fallbacks were invisible.** When the Hub times out or a `git`
   subprocess fails, the code degrades to a local write / `None` with no record
   of *why*. For an observability tool, an un-observable fallback erodes trust
   and makes user-environment debugging impossible.
3. **No test exercised the Hub-timeout fallback.** Real `HubServer` tests
   exist, but none injected latency past the client timeout to prove the
   degrade-to-local-write path actually works.

Explicitly **not** done (review items rejected as wrong/overstated): raising the
150 ms loopback timeout (it is a deliberate fail-fast to a guaranteed local
write — raising it makes hooks hang longer on a dead Hub), and a FastAPI
rewrite of the dashboard.

## What changes

1. **Reader shared lock.** New `read_locked_file()` acquires `LOCK_SH`
   (`_acquire_read_lock`: `fcntl.LOCK_SH` on POSIX, no-op on Windows where
   `msvcrt` has no shared mode). `parse_sessions` and `unattributed_log_count`
   read through it; `_iter_log_lines` now takes a file handle so the caller
   owns the locked open. A writer's `LOCK_EX` blocks a reader's `LOCK_SH` for
   the duration of the append, so no torn line is observed.
2. **Diagnostic log.** New `log_diagnostic()` appends a one-line, never-raising
   entry to `~/.halyard/diagnostic.log` (separate from the existing audit
   `halyard.log`). Wired into `hub_client._request` (every degrade-to-None) and
   all `git_context` subprocess error/timeout paths.
3. **Latency regression test.** A real `HubServer` whose `do_POST` sleeps past
   the 150 ms client timeout proves `append_session` falls back to a local
   write and records the reason.

## Impact

- Affected: `src/halyard/ai_log.py` (read lock + `log_diagnostic` +
  `_iter_log_lines` signature), `src/halyard/hub_client.py` (diagnostic on
  fallback), `src/halyard/git_context.py` (diagnostic on every git failure).
- New file: `~/.halyard/diagnostic.log` (best-effort; absence is never an
  error). No change to the `ai-sessions.log` format or any public contract.
- Tests: `tests/test_v53_concurrency_observability.py` — cross-process
  shared-lock wait, `log_diagnostic` unit + never-raises, Hub-timeout fallback.
- Windows: the shared read lock is a documented no-op (msvcrt has no shared
  mode), matching the pre-existing writer-lock platform note.
