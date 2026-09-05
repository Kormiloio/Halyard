# Design: v5.26 — Auto-timer under-count

## Root cause, precisely

Three facts combine:

1. The Stop hook *does* refresh — `claude_code.handle_stop_hook` calls
   `auto_timer_update_activity()` (claude_code.py:612) — but that
   function returns early when no window is open (`if not state:
   return`). It can refresh, never reopen or backfill.
2. The idle policy closes a window **at `last_activity`**, not at the
   moment of closing — so the elapsed gap is discarded, not billed and not
   flagged.
3. Two independent components apply that policy:
   `auto_timer.auto_timer_close_if_stale()` and
   `hub_server._close_stale_presence()`. The Hub's runs whenever presence
   is polled, which The Bridge does continuously.

So a long turn is closed out from under itself at ~30 minutes, and the
Stop that finally arrives two hours later finds nothing to refresh and
silently does nothing. Counted time ≈ *prompt cadence*, capped at 30
minutes per prompt. Long agent turns — the normal shape of modern agentic
work — are invisible.

Note the fix is **not** "call the refresh from more places": the refresh
is already wired into the Stop path and would still no-op here. What is
missing is the ability to assert coverage for a span that has already
been closed.

## The fix: sessions are the evidence

Halyard already records, with timestamps, that work happened:
`s <start> <end> <tool> …`. The timeclock should not contradict its own
ledger.

Two changes, in order of importance:

### 1. `auto_timer_cover_session(project, timeclock, start, end)`

Called from every collector's stop hook after a session row is built.
Ensures the timeclock covers `[start, end]`:

- Merge into an open window whose `i` is at or before `start` — extend by
  moving nothing; the eventual `o` will be at or after `end`.
- If the span was closed early (the mid-turn stale close), append the
  missing remainder as a fresh `i`/`o` pair rather than rewriting history.
  Appending keeps the log append-only, which the format requires.
- **Never** extend beyond the session's own `end`. The session bounds the
  claim.
- Idempotent: a span already covered writes nothing.

This is the part that fixes the observed case. The 16:31→18:32 session
would append coverage for 16:31→18:32 regardless of what the stale close
did at 16:42.

### 2. Extend the refresh to the other collectors

`auto_timer_update_activity()` is wired into Claude Code's stop hook only;
`cursor`, `gemini_cli`, and `windsurf` never call it, so a user of those
tools has an even weaker signal. Wiring them up is cheap hygiene.

Alone this is **insufficient** — it no-ops exactly when it matters, once
the window has already been closed mid-turn — which is why (1) is the
primary fix and (2) is secondary.

### Both writers

Every change lands in `auto_timer.py` *and* `hub_server.py`. The Hub
mirrors the standalone logic today; if only one is fixed, machines
running The Bridge keep the bug and the fix looks like it works on the
developer's laptop.

`INACTIVITY_MINUTES` stays 30 and stays the single source of truth
(`hub_server` and `timeclock_repair` both derive from it).

## Retroactive recovery

`halyard timeclock repair --from-sessions`:

- Read `ai-sessions.log` for the same project.
- For each session span with no timeclock coverage, propose an `i`/`o`
  pair bounded by the session.
- Never propose a span that overlaps existing coverage — union, not sum.
- Dry-run by default, timestamped backup on `--apply`, unified diff —
  matching the existing `repair` contract exactly.

Report recovered hours so the user can see what the defect had cost them.

## Doctor check

`_human_time_coverage_check()`:

- For the trailing period, compare summed AI session time against counted
  human time for the same window.
- If human time is materially below AI time (proposed: < 50% with at
  least an hour of AI time, so short days do not trip it), warn — this is
  the defect's signature.
- `warning`, never `error`. Fix text points at
  `halyard timeclock repair --from-sessions`.

Threshold is a judgement call and should be tuned against real data
before shipping; the check is worthless if it cries wolf.

## Alternatives considered

- **Raise `INACTIVITY_MINUTES`.** Rejected: bills genuine idle time. The
  policy is not the bug.
- **Close stale windows at `now` instead of `last_activity`.** Rejected
  for the same reason — it bills the idle gap wholesale, and it would
  silently inflate every historical day.
- **Poll for presence (keyboard/IDE focus).** Rejected: out of character
  for a metadata-only local tool, and a new privacy surface for a problem
  the existing ledger already answers.
- **Derive human time entirely from session spans, dropping the
  timeclock.** Tempting and simpler, but it discards manual
  `halyard start/stop` entries and non-AI work, which the timeclock is
  also for. Coverage-merge keeps both.

## Testing

- A single prompt then a 2-hour turn → ~2 hours counted, not 30 minutes.
- Mid-turn stale close (simulating Hub polling) → the stop hook still
  recovers full coverage.
- Idempotence: replaying the same stop writes no duplicate coverage.
- No over-claim: coverage never extends past the session's `end`.
- Genuine idle between sessions is still excluded.
- Hub path and standalone path produce identical timeclocks for the same
  event sequence — the regression that would otherwise reintroduce this.
- `repair --from-sessions`: recovers a known-lost day; is idempotent; does
  not double-count already-covered spans; dry-run writes nothing.
- Doctor: fires on an under-counted day, silent on a healthy one, silent
  on a short day.
- `perf_ceiling` for any timing assertion; no wall-clock literals.
- Every test that touches a ledger or timeclock must `chdir` into
  `tmp_path` (see the v5.24 conftest guard — collectors resolve targets
  from cwd, so patching `Path.home()` alone is not enough).


---

## Implementation notes (amending this design)

### The `hub_server` mirror turned out to be unnecessary

This design required every change to land in `auto_timer.py` **and**
`hub_server.py`, on the reasoning that the Hub applies the idle policy
independently and wins on any machine running The Bridge.

That holds for anything routed through the presence state machine. It does
not hold for the fix as built. `auto_timer_cover_session` reads the
timeclock with `parse_timeclock` and appends with `locked_file` — it never
calls `_try_hub_presence` or `_read_state`. Coverage is asserted against the
timeclock **file**, so it is indifferent to whether the Hub already closed
the window mid-turn; the gap is simply still a gap, and gets filled.

Sidestepping the two-writer problem rather than duplicating logic into it is
the better outcome: the original framing would have left two copies of the
same interval arithmetic to drift apart.

`test_coverage_is_independent_of_presence_state` pins this by making
`_try_hub_presence` raise if called, because a future refactor that routed
coverage through presence would silently reintroduce the bug on exactly the
machines that had it.

### Scope actually shipped

Only the **core fix** — the part that stops the ongoing under-count:

- `auto_timer_cover_session` + `_uncovered_spans` (union semantics,
  append-only, session-bounded, idempotent)
- `safe_cover_session`, wired into all four stop hooks (`claude_code`,
  `cursor`, `gemini_cli`, `windsurf`) — previously only `claude_code`
  touched the auto-timer at all

Deferred to a follow-up, and **not** attempted here:

- `halyard timeclock repair --from-sessions` (retroactive recovery of days
  already lost). Real user value — this is what recovers the observed
  2026-08-11 day — but it is a new user-facing CLI mode with a
  backup/dry-run/diff contract of its own.
- `_human_time_coverage_check()` in doctor. The design itself flags the
  threshold as needing tuning against real data before shipping, and a
  check that cries wolf is worse than no check.
- README wording on what auto-detected human time counts.

Splitting here keeps the reviewable unit small and gets the bleeding
stopped; the deferred parts are recorded in `tasks.md` rather than dropped.
