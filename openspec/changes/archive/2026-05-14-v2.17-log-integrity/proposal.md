# Proposal: v2.17 — Log Integrity

## Why

The v2.15 deep code review identified four data-integrity issues with the
plain-text logs that v2.12 (dashboard-as-service) made permanent:

- **C3 — No file locking.** `append_session` and three log-rewriting
  functions (`assign_unattributed_sessions`, `confirm_session_attributions`,
  `backfill_window`) operate without locks. Concurrent calls can clobber
  each other's writes.
- **C4 — `halyard stop` races itself.** The active-timer file has no lock,
  and `unlink()` is called without `missing_ok=True`. CLI stop and
  dashboard `/api/stop` can both pass the existence check and produce
  duplicate `o` lines in `time.timeclock`.
- **H3 — `except Exception: pass` swallows backfill errors.** Combined
  with C3, this means a corrupt log can produce silent-empty data forever
  with no signal to the user.
- **M3 — Append-only invariant violated.** `confirm_session_attributions`
  and `backfill_window` rewrite the log in place. The strategy doc names
  the open append-only protocol as a moat. Mutating logs in place breaks
  the trust contract that makes other tools willing to emit our format.
- **H7 — Invoice counter is not atomic.** `halyard.toml` is read, mutated,
  and rewritten without a lock. Concurrent `halyard invoice` calls can
  collide.
- **M4 — Single global timer per machine.** Documented here for completeness;
  a deferred fix to v2.19.

## What changes

1. **Correction-record line type.** Add a new line format to
   `ai-sessions.log`:

   ```
   a <session_hash> [key=value ...]
   ```

   This is an **a**mendment record applied at parse time. Instead of
   rewriting the original `s` line, attribution functions append an `a`
   line. Parsers fold the latest `a` for each `session_hash` over the
   original `s` line during read.

2. **File locking on all mutators.** Use `fcntl.flock(LOCK_EX)` on:
   - `ai-sessions.log` for any append or rewrite (rewrites become rare;
     see below)
   - `time.timeclock` for clock-in / clock-out
   - `~/.halyard/active.timer` for start/stop transitions
   - `halyard.toml` for invoice counter increments

3. **Replace in-place rewrites with corrections.**
   - `assign_unattributed_sessions` — emits `a` records.
   - `confirm_session_attributions` — emits `a` records.
   - `backfill_window` — emits `a` records.
   - The legacy `_rewrite_lines_atomic` path is retained only for
     destructive operations the user has explicitly requested
     (`halyard log purge`, future GDPR-style erasure).

4. **Shared `start_timer` / `stop_timer` in orchestration.** The CLI and
   dashboard call the same orchestration function. The dashboard's
   duplicate logic in `do_POST` is removed. `halyard backfill` is invoked
   from the shared `stop_timer`, fixing the H1 dashboard-skips-backfill
   regression.

5. **`unlink(missing_ok=True)`** on the active-timer file in `stop`.

6. **Loud error reporting.** Replace `except Exception: pass` in stop and
   sync paths with explicit logging: print a one-line `[warning]` to the
   user, write the full traceback to `~/.halyard/halyard.log`, and exit
   the relevant command with non-zero only for the most critical paths.

## What stays the same

- The `s` line format is unchanged. Existing logs parse identically.
- `parse_sessions` returns the same `AiSession` objects, with attribution
  fields now reflecting any folded `a` records.
- The plain-text trust posture: humans can read the log, see the
  amendments, and reason about every change.

## Out of scope

- Cryptographic tamper-evidence (signed log lines). Listed as a strategy
  goal but deferred to v3.x.
- Multi-timer support (M4). Deferred to v2.19.
- Anything other than `s` and `a` line types (no `i`, `t`, etc.).
- Replacing the timeclock format (still ledger-style i/o pairs).

## Success criteria

- Append-only invariant holds: no function in `ai_log.py` calls
  `write_text` on the log except in user-driven destructive operations.
- The `a` record format round-trips: writing then reading yields the
  expected attribution.
- Concurrent writes test: 100 simultaneous `append_session` calls produce
  exactly 100 lines, no corruption, no missing records.
- `halyard stop` from CLI and `POST /api/stop` from dashboard produce
  identical state changes (timeclock entry, attribution backfill, log
  amendments).
- Race regression test: simultaneous CLI stop + dashboard stop produce
  exactly one `o` line in the timeclock and one set of `a` records.
- Loud errors: a malformed log line in backfill produces a visible
  warning and a `~/.halyard/halyard.log` traceback, not a silent skip.
