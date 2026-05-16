# v2.53 — Parse-Time Synthetic-Telemetry Guard

## Problem

The data-correctness chain v2.45–v2.49 added guards in Halyard's *hook
collectors* (require a session start, drop evidence-free / implausible
sessions). But the contaminating writer — the thedotmack claude-mem
`worker-service.cjs` daemon — appends canned rows to `ai-sessions.log`
**directly**, never going through a Halyard collector. So every
write-time guard is bypassed by construction.

Confirmed on 2026-05-15: 18 synthetic rows (9 Cursor + 9 Gemini)
landed *today*, in tight bursts, while the v2.49 guard was live. Their
fingerprint is exact and machine-stamped:

- Cursor: `input=2000, output=400`, model `claude-3.5-sonnet`,
  `cost=0`, no project
- Gemini: `input=100, output=50`, model `gemini-2.0-pro`,
  `cost=0`, no project

The guard must move from the **writer** (which an external process
skips) to the **reader** (which every Halyard surface shares).

## Goal

A parse-time predicate that recognizes the claude-mem canned
fingerprint and excludes those rows from everything Halyard reads —
CLI, dashboard, aggregate, and the v2.50 MCP server — via the single
chokepoint `ai_log.parse_sessions`.

- New `collectors.session_is_synthetic_telemetry(session)` predicate.
- `parse_sessions` filters matching rows out of its result.
- Same predicate also `or`-ed into the existing collector write guards
  (defence in depth — Halyard's own collectors never emit it either).

## Constraints honored

- **Tight fingerprint, zero false positives.** A row is synthetic
  only if **all** hold: `cost_usd == 0` AND no project AND
  `(input,output)` is exactly `(2000,400)` or `(100,50)` AND model is
  exactly `claude-3.5-sonnet` or `gemini-2.0-pro`. Real current work
  (Opus/Sonnet-4.x, nonzero cost, attributed) cannot match.
- **No deletion, no mutation.** The raw `s` line stays in
  `ai-sessions.log` (immutable, auditable). It is simply not surfaced.
  No quarantine write either — parse runs on every render, so writing
  would grow unbounded; exclusion is idempotent and side-effect-free.
- **One chokepoint.** Filtering in `parse_sessions` covers every read
  path with no per-surface changes.

## Non-goals

- Physically purging existing synthetic lines from logs (a separate
  manual `halyard check-log`-style operation; out of scope here).
- Heuristic/ML detection — only the exact known canned fingerprint.
- Stopping the external daemon (operational; handled separately).

## Out of scope

A general pluggable "untrusted external writer" framework — premature;
revisit only if a second such writer appears.
