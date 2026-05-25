# ADR 0001 — Timezone model: naive-local domain time, UTC for machine logs

- **Status:** Accepted
- **Date:** 2026-05-24
- **Deciders:** Halyard maintainers
- **Supersedes/relates:** roadmap v2.29 (item 6, "standardized to local-naive
  across all collectors"), v2.38 (PR-attribution datetimes normalized to UTC),
  v2.56 P1-a (`parse_sessions` coerces tz-aware rows at the boundary)

## Context

Halyard records two different *kinds* of time:

1. **Domain time** — when AI/human work actually happened: `s` session
   `start`/`end` in `ai-sessions.log`, `i`/`o` entries in `time.timeclock`.
   This is wall-clock time a human reasons about ("I worked Tuesday
   afternoon"). It is written by collectors and read back into reports,
   invoices, streaks, heatmaps, and the dashboard.
2. **Machine time** — internal bookkeeping: `~/.halyard/halyard.log` audit
   entries, the new `~/.halyard/diagnostic.log` fallback records, and the
   resolved-at timestamps on PR/outcome attribution.

Today these are handled inconsistently *by design*, but that design was never
written down, so each review re-litigates it. A reviewer recently flagged
"timezone naivety" as a $10M-scale enterprise risk. This ADR records what the
model actually is, why, and what would have to change before multi-team
aggregation is mathematically sound.

### Current behaviour (verified 2026-05-24)

- Collectors stamp sessions with **naive local** time: every collector uses a
  bare `datetime.now()` / `strftime("%Y-%m-%dT%H:%M:%S")` with no offset
  (`collectors/claude_code.py`, `cursor.py`, `gemini_cli.py`, `windsurf.py`,
  `vscode_otel.py`).
- The on-wire format carries **no timezone offset**:
  `start.strftime("%Y-%m-%dT%H:%M:%S")` in `AiSession.to_log_line`.
- The read path is defensive: `_to_naive_local()` (`ai_log.py`) converts any
  tz-aware row (hand-edited, or from an older/foreign writer) to the local
  wall clock and drops `tzinfo`, so all downstream math compares naive against
  naive `datetime.now()` and never raises the aware/naive `TypeError`.
- Machine logs use **UTC**: `_log_error` and `log_diagnostic` write
  `datetime.now(tz=UTC).isoformat()`. PR/outcome resolution timestamps are
  normalized to UTC (v2.38).

## Decision

**Domain time stays naive-local. Machine time stays UTC. The split is
intentional and is the documented contract.**

Concretely:

1. Session and timeclock timestamps are **naive local wall-clock** with no
   offset in the plain-text files. This is the human-meaningful, diff-friendly
   representation and matches the hledger timeclock and Beancount conventions
   Halyard already commits to (a freelancer's ledger is a local-time
   artifact).
2. The read boundary (`_to_naive_local`) is the **single coercion point**.
   Any tz-aware input is folded to naive local there; no other module branches
   on `tzinfo`.
3. Internal logs (`halyard.log`, `diagnostic.log`) and cross-service
   attribution (PR merge/resolve times) use **UTC**, because those are machine
   events compared across hosts, not human-scheduled work.

### Rationale

- **Local-first, plain-text-forever (project non-negotiables).** The files are
  the source of truth and must read naturally to a human in their own
  timezone. Storing `2026-05-06T20:50:14-04:00` in every row buys nothing for
  the single-user wedge and makes the format noisier to diff.
- **One coercion point beats N branches.** Mixing aware and naive datetimes is
  the actual bug class (it raises `TypeError` mid-report). Funnelling every
  read through `_to_naive_local` is what keeps that from happening, regardless
  of what a foreign writer emits.
- **UTC where it's unambiguous.** Logs and PR events have no "human's
  timezone" — they're sequential machine facts — so UTC is correct there and
  already in place.

## Consequences

### Positive
- No aware/naive `TypeError` regressions as long as new readers go through the
  documented boundary.
- Files stay human-readable and tool-compatible (hledger/Beancount).
- The decision is now citable; reviews stop re-opening it.

### Negative / known limitation (the enterprise gate)
- **Cross-timezone aggregation is not sound today.** Two teammates in
  different zones produce `s` rows whose naive timestamps are *not* directly
  comparable: a "9am" in New York and a "9am" in Berlin sort as equal. Any
  future **Halyard-Enterprise** redacted-sync / cross-team rollup that merges
  ledgers from multiple hosts MUST resolve offsets before aggregating.
- Naive local time is also ambiguous across DST transitions (the repeated 1–2am
  hour in fall). Acceptable for solo wall-clock reporting; not acceptable for
  billing arbitration across parties.

### Future direction (not built; gated on Halyard-Enterprise pull)
When cross-team aggregation is actually on the roadmap, the migration is
**additive, not a rewrite of history**:
1. Add an **optional** `tz` token (IANA name, e.g. `tz=America/New_York`) to
   the `s` line via the v2.75 extensible-token path — byte-stable for existing
   rows, which are interpreted as "writer's local zone" exactly as today.
2. Enterprise sync converts `(naive_local, tz)` → UTC instant **at the
   aggregation boundary only**; the OSS single-user surfaces keep rendering
   local wall-clock.
3. Existing tz-less history remains valid: absent `tz` means "local to the
   reader," the current behaviour.

This keeps the OSS format untouched, avoids retro-corrupting any existing
ledger, and defers the cost to the layer that actually needs it.

## Alternatives considered

- **UTC-internal everywhere, localize at the edge (the reviewer's
  suggestion).** Correct for a distributed system; wrong cost/benefit for a
  local-first plain-text tool. It would make every file row carry machine time
  a human has to mentally convert, and force a breaking format migration for
  zero single-user benefit. Rejected now; partially adopted later via the
  optional `tz` token above.
- **Offset-aware timestamps in every row (`...-04:00`).** Captures the instant
  but not the zone (can't render DST-correct future/past), adds per-row noise,
  and still needs a coercion boundary for legacy rows. Rejected.
