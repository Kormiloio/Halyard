# Design: v3.14 — Gemini session de-duplication

## The invariant being restored

One Gemini CLI session = one ledger session. Today an N-turn session yields up to
N+1 rows because the whole-session history file is read by both the per-turn hook
and the importer.

## Why read-time, not write-time

The project's established pattern (v2.53 synthetic guard, v2.54 future-date guard,
v2.62 token normalisation) is to keep the append-only log immutable and normalise
at the `parse_sessions` read chokepoint. That choice is doubly right here:

- `parse_sessions` is the single function all 20 counting surfaces call (report,
  dashboard, aggregate, budget, MCP, status, invoicing, db, tui, …), so one edit
  fixes every surface.
- It **retroactively** corrects the rows already in the log (the `70615981`
  session) without a risky in-place rewrite of user data.

A write-path alternative (hook emits per-turn *deltas*; importer skips
hook-covered sessions) was rejected: it leaves the existing polluted rows wrong,
adds fragile delta state to the hook (a single missed write corrupts every
subsequent delta), and would still need read-time reconciliation between the
delta rows and the importer's total row. The hook's cumulative snapshot already
*is* the correct running total, so "keep the maximal row per session" needs no
write change.

## The collapse

`ai_log.collapse_gemini_sessions(sessions) -> sessions`:

- **Key:** `_gemini_session_key(s)` returns a session id only for
  `tool == "gemini-cli"`, resolved from `s.session_id` (hook rows) or
  `s.job_id` of the form `gemini:<id>` (importer rows). Both shapes — and rows
  already written — resolve to the same key.
- **Grouping:** rows with no key (non-Gemini, or a Gemini row lacking any id)
  pass through unchanged, preserving order. Rows sharing a key are grouped; the
  group is emitted once, at the position of its first member.
- **Canonical pick:** `max` by
  `(input_tokens + output_tokens, project_present, window_seconds, cache_read)`.
  Most-complete wins; ties prefer the attributed row, then the wider window. This
  keeps the hook row carrying `project=kormilo/halyard` over the unattributed
  importer row when totals match.
- **Idempotent:** running it twice is a no-op, so applying it in both
  `parse_sessions` and the aggregate merge is safe.

### Application points

1. End of `parse_sessions`, wrapping the already-filtered (synthetic/future)
   list. Fixes same-log duplicates (the common case; this exact session).
2. `reports.build_aggregate_dashboard_state`, after `_dedup_sessions(merged)`,
   for the rare cross-log case (hook wrote to the project log, importer to the
   hub).

## Defect C — utility model (limitation, not fixed)

`gemini-3.1-flash-lite` (`utility_router`/`utility_summarizer`) is absent from the
session `.jsonl`; only `gemini-3-flash-preview` events are persisted. The
history-derived collectors therefore cannot see it. The `/quit` terminal summary
has it but is not a persisted, parseable artifact; OTel (v2.67) carries durations,
not per-model token counts. Recorded in `docs/collector-coverage.md` as a known
gap rather than papered over. ("Unavailable is not zero" — no fabricated row.)

## Verification

A unit test reconstructs the three real `70615981` rows (two hook cumulative
snapshots + one importer row) and asserts they collapse to one row with
59,970 / 1,451 / 170,196 and `project=kormilo/halyard`. Further tests cover a
3-turn hook-only session, distinct-session non-collapse, non-Gemini pass-through,
and idempotency.
