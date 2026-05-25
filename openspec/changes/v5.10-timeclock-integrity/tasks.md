# Tasks — v5.10 Timeclock integrity

## Part 1 — root cause (Hub presence persistence)
- [x] `auto_timer`: `write_presence` / `read_presence` / `clear_presence`
      public helpers over the existing state file.
- [x] `hub_server._persist_auto_presence_locked()`; call from
      `_record_presence_activity` + `_update_presence`; clear from
      `_close_presence_now`.
- [x] `hub_server._reconcile_auto_presence()`; call from `_load_state()`
      (resume if recent, close-stale if old).
- [x] Tests: reconcile resume, reconcile close-stale, persist round-trip,
      malformed-file clear.

## Part 2 — repair tool
- [x] `timeclock_repair.reconstruct_timeclock(lines) -> list[str]` (merge auto
      runs, preserve manual verbatim, drop orphan o, trailing-open rules,
      backward/far-future close guards).
- [x] `cli_timeclock.py`: `check` (read-only) + `repair` (`--apply` after
      timestamped backup, diff-and-confirm dry-run default); register in `cli.py`.
- [x] Tests: reconstruct cases + `check`/`repair` CLI (16 tests).

## Part 3 — test-isolation leak (second root cause)
- [x] `conftest._isolate_auto_timer` autouse redirects `_AUTO_TIMER_FILE` for
      all tests.
- [x] `test_auto_timer.py` reads the patched module attribute; real-file unlink
      fixture removed.
- [x] Proven: seeded real state survives a suite run.

## Data remediation (this machine)
- [x] Repaired the ledger. Faithful reconstruction (trust clean closes, cap
      dropped-open runs) = 60.9h/82 windows; per user judgment the two long
      unattended `git/Halyard` windows (14.2h overnight, 9.3h) were capped to
      30 min each → **38.5h applied**, check 0/0, idempotent. Backups:
      `time.timeclock.bak-20260525T180557Z` (raw) + `…bak-precorrect-*`.
      (An earlier cap-everything draft applied 33.3h; corrected after finding it
      crushed legit single-`i` long sessions.)
- [x] `outcome sync`: 425 sessions resolved (all "no PR" — direct-to-main, no
      PRs exist); "not synced" flag cleared.
- [x] `backfill`: 1 confident match applied; remaining 55 left as-is per user
      ($2.92 total, no remote/branch — no metadata to attribute). `[outcomes]`
      already defaults on; no config change needed.

## Close-out
- [x] ruff + ruff format + mypy clean; full pytest green (1536).
- [x] design.md deviations recorded (merged-flag clock-out handling, idempotency
      gate, trailing-open, Part 3 test isolation).
- [x] project.md roadmap entry (84) + test count.
- [ ] Commit.
