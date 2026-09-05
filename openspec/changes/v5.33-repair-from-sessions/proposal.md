# v5.33 — Recover the hours the auto-timer already lost

## Why

v5.26 stopped the bleeding: new sessions now assert timeclock coverage for
the span they prove. It did nothing for days already lost, and the loss is
large. On the machine that motivated it the timeclock counts **8.4 h**
across a 40-day capture window in which the session ledger records work
throughout — an order of magnitude under-count of billable time, already
written down.

The ledger is the evidence. `halyard timeclock repair --from-sessions`
reconciles the timeclock against it after the fact, proposing coverage for
any span a recorded session proves but the timeclock does not cover.

Deferred out of v5.26 deliberately: it is a new user-facing mode with its
own safety contract, and mixing it into the core fix would have made both
harder to review.

## The finding that shaped the design

The first working implementation proposed **647.2 hours**.

That is ~27 days of continuous time, and it came from two long-lived
*imported* Codex rollouts — one spanning 08-09 to 09-05 (653 h, still open),
another 149 h. Together they were **89% of all recorded session time** on
that machine, from 2 of 52 sessions. Everything else was ≤ 12 h.

v5.26's proposal anticipated over-claiming and judged the session bound
sufficient:

> Bounding coverage to the session's own start/end (never extending past
> it) keeps this defensible

That reasoning holds at hour scale and collapses at month scale. A Codex
session left open for four weeks is a background process, not four weeks of
human work. Applied unguarded, this feature would have produced an
invoice-destroying number from a mostly-idle process — the exact opposite of
the under-count it exists to fix, and far more damaging.

## What

`--from-sessions` on the existing `timeclock repair` command:

- Propose coverage only for spans a session proves and the timeclock lacks.
- **Union, never sum.** Coverage already present — including coverage
  proposed for an earlier session in the same run — suppresses a later
  proposal, so overlapping sessions cannot double-bill.
- **Never outside a session's own `[start, end]`.**
- **Skip sessions longer than `_MAX_SESSION_SECONDS`.** Not a new magic
  number: the collectors already cap a live session at 12 h, so a row past
  that is, by the codebase's own standard, not one sitting of work. Skipped
  rather than clamped — clamping to the first N hours would assume the work
  happened at the start, which is a guess. The skipped total is reported so
  the user can see what was excluded and why.
- Same safety contract as the existing repair, shared through one code
  path: dry-run by default, unified diff, timestamped backup before any
  write, atomic replace.

With the bound in place the same machine proposes **71.9 h** — 8.4 h → 80.3 h,
or 2.0 h/day across the window.

## Out of scope

- The doctor coverage check from the v5.26 spec. Its threshold still needs
  tuning against real data, and a check that cries wolf is worse than none.
- Any change to what the live path claims. v5.26 is wired only into the four
  hook-driven collectors, whose sessions are capped at 12 h by construction;
  imported long-lived rollouts never reach it.
