# Proposal: v3.2 — Struggle signals (surface only)

## Why

v3.0 answers "did the AI work ship?"; v3.1 answers "what did shipping
cost in review?". Neither shows *in-session struggle* — how much the AI
thrashed before producing the work. Two signals already capture this:

- **`tool_errors`** — failed tool calls in a session. A collector audit
  (2026-05-18, recorded in `design.md`) confirms **all four collectors**
  (claude_code, cursor, gemini_cli, codex_app) already compute and emit
  it; it round-trips through the log today.
- **`rejected_suggestion_count` / `accepted_suggestion_count`** — the
  human rejecting AI output. The same audit found this is captured by
  **Cursor only**; the other three collectors do not emit it.

So the data is already there — `tool_errors` universally, rejections
partially — but **nothing surfaces it**. There is no report bucket, no
Leverage line, no invoice row for struggle. This changeset closes that
gap with a *surface-only* change: zero new capture, zero schema change.

This is the v3.1-shaped slice of the v3.0-deferred "tool errors /
approval rejections" workstream — the part where the substrate already
exists. The expensive part (making rejections cross-collector) is
explicitly **out of scope** (see below).

## What changes

Surface the two already-captured signals, honestly trust-labelled:

- **Outcome report** — each bucket gains a struggle sub-line: total
  `tool_errors` and the tool-error rate (errors / tool_calls) over the
  bucket; rejections shown only when the bucket has capture coverage.
- **Leverage panel (web + TUI parity)** — a one-line struggle summary
  under the existing rollup: median tool-error rate, and rejection rate
  *only* over sessions whose `interaction_data_available` is true.
- **Invoice evidence appendix** — per-PR struggle is **not** added
  (kept lean; struggle is an internal signal, not client-facing). The
  appendix is unchanged.
- A new shared `struggle` summary on `leverage.summarize`'s path so web
  and TUI cannot diverge (same pattern v3.1 used).

Honesty about asymmetric capture is the core requirement:

- A session with `interaction_data_available = false` (or unset)
  contributes to tool-error stats (universal) but is **excluded** from
  the rejection-rate denominator — it is "not captured", not "zero
  rejections". Surfaces state the rejection coverage explicitly
  (e.g. "rejections: 12 over 34 Cursor sessions (other tools: not
  captured)").

## What stays the same

- No collector changes. No new capture path. No new log token. No
  schema/migration. Surfaces read already-parsed `AiSession` fields
  (`tool_errors`, `tool_calls`, `accepted/rejected_suggestion_count`,
  `interaction_data_available`) — the plain-text log stays the source
  of truth.
- Privacy: these are the v2.32 privacy-safe integer/boolean fields —
  counts only, never prompts/code/tool names. No new egress. The v3.0
  privacy contract holds verbatim.
- `outcomes.enabled = false` is unrelated (this is not an outcome-sync
  signal); struggle surfacing is gated by the same data being present,
  and absent data renders the surface exactly as before.

## Out of scope

- **Cross-collector rejection capture** (claude_code hooks, gemini_cli,
  codex_app emitting `rejected_suggestion_count`). This is the real
  collector work v3.0 deferred; it gets its own changeset. v3.2
  surfaces only what Cursor already provides, clearly labelled.
- **MCP-server inventory** — greenfield, no field, no capture path; a
  separate future changeset.
- Tool-error *classification* (which tool, why) — would require
  capturing tool names; violates the privacy contract. Counts only.
- Any LLM judgement of "was this struggle bad". Surfaces signals;
  humans interpret.

## Prerequisites

- v3.0 + v3.1 complete (they are).
- Phase-0 collector-coverage audit complete — findings recorded in
  `design.md`. No spike outstanding; this is surface-only over audited
  fields.

## Success criteria

1. `outcome report` shows tool-error count + rate per bucket; renders
   byte-identical to v3.1 for sessions with no tool_calls data.
2. Leverage panel (web + TUI) shows the struggle line only when data
   exists; the two surfaces show identical numbers (shared summary).
3. Rejection stats are computed only over
   `interaction_data_available = true` sessions and every surface
   states the coverage; a non-Cursor-only run never displays a
   misleading "0 rejections".
4. No schema change, no new log token, no collector diff (enforced by
   a test asserting `git diff --stat` touches no `collectors/` file —
   or simply: no collector file imported/modified).
5. ≥15 new tests: per-bucket struggle math, the availability-gated
   rejection denominator, web/TUI parity, absent-data v3.1-identical
   rendering, and a privacy assertion (only ints/enum reach surfaces).

## Strategic implication

v3.0 = did it ship. v3.1 = what did review cost. v3.2 = how much did it
thrash to get there. Together that is the leverage triad a CTO asks
about — and v3.2 ships it with no new data collection at all, purely by
honestly surfacing what Halyard already records.

## Detailed design

See `design.md`.
