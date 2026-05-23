# Proposal: v3.9 — Claude Code Stop-hook catch-up (silent under-capture)

## Why this exists

A ground-truth audit (ledger vs. the Claude Code transcript) found the
**primary tool was capturing only ~1/3 of real usage**. A completed
2026-05-22 session: transcript = 33 user turns / 194,062 output tokens /
168 tool calls; ledger = 15 rows / 68,390 output (**35%**) / 54 tool calls.
Mapping rows to turns showed only 12 of 33 turns landed in a row window,
with a **~6-hour stretch (08:58→14:48) of active work and zero rows**.

Root cause: capture depends on `UserPromptSubmit` **and** `Stop` firing in
lockstep. `record_session_start` writes the turn start to a single
`cc-session` file (only if absent); `handle_stop_hook` reads it, **clears
it**, and records `[start, now]` reading the transcript only `since=start`.
When `Stop` is missed for a stretch (common in the desktop app), those turns
are dropped — and there is **no catch-up**: the next turn starts fresh from
its own `UserPromptSubmit`, so the gap is lost permanently. If `Stop` fires
with no `cc-session` at all, `start` defaults to `now` and the read captures
nothing.

## What changes

`handle_stop_hook` now anchors the transcript read to a **high-water mark** —
the latest `end` already recorded for this `session_id` in the ledger
(`_last_recorded_end`) — instead of just this turn's start. One `Stop` after a
gap then back-fills everything since the last recorded row. The transcript is
the cumulative source of truth; the ledger is the watermark, so capture is
catch-up-safe and idempotent regardless of how unreliable the hook pairing is.

- First turn of a session (no prior row) → no watermark → unchanged
  (`since = cc-session start`).
- Subsequent `Stop` → `since = last recorded end`, so missed turns in the gap
  are recovered.
- Windows stay contiguous and non-overlapping (next `since` = prev `end`), so
  no double-counting.

## Scope / limits

- This recovers any gap **as long as `Stop` fires at least once after it**
  (e.g., the next turn, or session end). A session that is killed with no
  further `Stop` still loses its tail — covered by the planned scheduled
  transcript reconcile (v3.11 workstream) and flagged by the v3.10 doctor
  coverage canary.
- Historical backfill of already-lost rows is **not** done here (the live fix
  is forward-looking); the reconcile importer handles backfill.
- Reads `parse_sessions(project_dir)` once per `Stop` (O(n) over the log) —
  same order as the existing append.

## Success criteria

- A `Stop` after a missed-turn gap records a row whose tokens include the gap
  turns (regression test).
- Existing single-turn behavior unchanged; full suite green; ruff/mypy clean.
