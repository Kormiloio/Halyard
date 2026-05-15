# v2.38 — Review Hardening

## Problem

A full codebase review (69 files, ~18k LOC) surfaced a batch of correctness,
security, and robustness defects. None are visible in the green test suite
because they live at the edges: float rounding that only compounds across
thousands of sessions, caches that poison cross-project reads, untrusted
strings reaching Rich markup, and cross-module spend totals that disagree.

Most are exempt bug-fixes/refactors, but three change an observable contract
and require a spec:

1. **Money math moves from binary float to `Decimal`.** Computed cost values
   change in the least-significant places. This is the headline contract shift.
2. **Spend totals are unified.** `halyard budget`, invoicing, and the ledger
   currently sum "cost" with different filters and window boundaries, so the
   same period shows different numbers in different views.
3. **`halyard adopt` rejects malformed project slugs** instead of writing
   corrupt TOML.

## Goals

- Cost is computed and rounded deterministically (`Decimal`, `ROUND_HALF_UP`).
- One shared spend-summing helper with one window convention, used by budget,
  invoicing, and ledger.
- No untrusted session-derived string can corrupt the TUI or inject TOML.
- Process-global caches are correctly scoped; no cross-project poisoning.
- Crash/concurrency atomicity for the trusted-state sidecar and the
  unattributed-log rewrite.
- TUI memory is bounded (retained sessions capped); moving aggregation
  off the event loop is a tracked follow-up (see design.md — needs an
  interactive run to validate).

## Non-goals

- No new user-facing commands or data formats.
- No change to the `ai-sessions.log` line schema.
- No re-pricing of historical sessions (cost is recomputed on read as today).
- No refactor beyond consolidating already-duplicated logic flagged in review.

## Out of scope

Architectural extraction of the three near-duplicate collectors into a shared
base is deferred — this changeset hardens them in place.
