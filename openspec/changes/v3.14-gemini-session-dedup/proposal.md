# Proposal: v3.14 — Gemini session de-duplication (stop multi-turn over-count)

## Why this exists

A live Gemini CLI session (`70615981-…`, observed 2026-05-23) was captured
**~2.5× over**. Its `/quit` summary reported the `gemini-3-flash-preview` work as
59,970 input / 1,451 output / 170,196 cache. The ledger held **three** rows for
that one session totalling 147,186 / 2,990 / 365,090 after the existing read-time
dedup ran.

Root cause — the Gemini history file is the **whole-session** record, and two
capture paths each read all of it:

1. **Hook cumulative over-count (Defect A).** On every `AfterAgent` fire,
   `gemini_cli.handle_agent_stop` re-parses the *entire* history file and writes
   the **running cumulative total** as that turn's row
   (`net_input = history_summary.total_input`). A 2-turn session emits
   `cumulative@turn1` (27,246) **and** `cumulative@turn2` (59,970, the full
   total); summing them re-counts turn 1. An N-turn session over-counts.
2. **Hook ↔ importer duplicate (Defect B).** `import-gemini` parses the same
   whole-session file and appends one more full-session row (59,970), duplicating
   the hook's final row. `reports._dedup_sessions` misses it because the import
   row has a different `start` and no `project`, so its dedup key differs.

A separate, **non-fixable** finding:

3. **Utility-model usage isn't in the history source (Defect C, limitation).**
   The `/quit` summary shows a second model — `gemini-3.1-flash-lite`
   (`utility_router` + `utility_summarizer`: 3 reqs, 11,747 in / 109 out) — but
   that model appears **nowhere** in the session `.jsonl` (only the 13
   `gemini-3-flash-preview` events are persisted). Halyard's history-derived
   collectors cannot capture what Gemini never writes to history. Documented
   honestly; not claimed as captured.

## What changes

- **A read-time Gemini session collapse.** `parse_sessions` (the one choke point
  all 20 counting surfaces share) collapses every row belonging to the same
  Gemini session id into a single canonical row — the most complete (max
  input+output), tie-broken toward the better-attributed / wider-window row. The
  session id is resolved from `session_id=` (hook rows) **or** `job_id=gemini:<id>`
  (importer rows), so both shapes — including rows already in the log — collapse.
  The same collapse is applied in the aggregate merge for the cross-log case.
- **No write-path change, no history rewrite.** Raw `s` lines stay in the file
  (immutable, auditable); they are simply collapsed at read time — the same
  philosophy as the v2.53 synthetic-row and v2.54 future-row read guards. This
  retroactively corrects the already-polluted ledger.
- **Honest limitation note** for Defect C in the collector-coverage docs.

## Out of scope

- Capturing the `gemini-3.1-flash-lite` utility/router model (not in the history
  source; only `/quit` and — for durations, not per-model tokens — OTel have it).
- Rewriting the append-only log to physically remove the redundant rows.
- Changing the hook to emit per-turn deltas. The cumulative snapshot the hook
  already writes *is* the correct running total, so "keep the maximal row per
  session" is exactly right and avoids fragile delta state.

## Success criteria

- The `70615981-…` session counts once: 59,970 / 1,451 / 170,196, attributed to
  `kormilo/halyard`, across every surface (report, dashboard, aggregate, budget,
  MCP, status).
- A multi-turn hook-only session and a hook+importer session each collapse to one
  canonical row; distinct sessions and non-gemini rows are untouched.
- ruff / mypy / full suite green.
