# v2.61 — Multi-Model Session Attribution

## Problem

A single agent session routinely uses **multiple models**. Observed in
Gemini CLI's own end-of-session summary: one session ran
`gemini-3.1-flash-lite` (router), `gemini-3-flash-preview` (main), and
`gemini-3.1-pro-preview` (main) — wildly different price points.
Claude Code (subagents/Haiku routing) and Codex (model routing) do the
same.

Halyard records **one `model` per session line**, and both cost
(`pricing.calculate_cost`) and every per-model rollup
(`usage._model_buckets`, `mcp_server._cost_by_model`, the dashboard
model table) key off that single field plus the session-level token
totals. `model_breakdown` exists but is a **display-only count
string** (`"model-a:3|model-b:1"`) that nothing costs against.

Net effect: a 3-model session's entire token + dollar total is
attributed to one model. The headline cost figure may still net out,
but **per-model cost and "favorite/most-expensive model" are wrong** —
and cost correctness is Halyard's moat. This is a data-correctness
defect, same family as v2.53–v2.59, not a cosmetic gap.

## Goal

Make a session's cost and per-model rollups correct when it spans
multiple models, without changing the one-line-per-session format.

- Generalise `model_breakdown` from counts to **per-model usage**
  (input/output/cache tokens per model).
- `calculate_cost`: when a per-model breakdown is present, cost is the
  sum of per-model costs; otherwise unchanged (single-model path).
- Per-model rollups (`usage`, `mcp_server`, dashboard) attribute by
  the breakdown when present, else fall back to `session.model`.
- `session.model` stays the **primary** model (max cost share) so the
  one-line summary and every existing consumer keep working.
- Collectors populate the breakdown: Cursor and Codex (new), Claude
  Code (the basic wiring from v2.60 upgraded to usage form), Gemini
  (upgrade its existing count-only breakdown to usage form).

## Constraints honored

- **Format preserved.** Still one `s` line per session; `model=` is
  the primary; the breakdown is one additional key=value token.
- **Backward compatible.** Old `model_breakdown=...:count` tokens and
  lines with no breakdown parse and cost exactly as today.
- **Unavailable is not zero.** No breakdown ⇒ single-model behaviour;
  never fabricate a split.
- **Cost is a sum of trusted parts.** Per-model cost uses the same
  `calculate_cost` + pricing table; trust labels unchanged.

## Non-goals

- Splitting one session into multiple `s` records (rejected — breaks
  the format and dedup/amendment hashing).
- Cache-pricing correctness itself (v2.62) — this change makes the
  *attribution* correct; v2.62 makes the *cache rate* correct. They
  compose.

## Out of scope

Sub-agent naming/hierarchy (Gemini's `main`/`utility_router` rows).
Model identity is enough for cost correctness; sub-agent taxonomy is a
later, separate concern.
