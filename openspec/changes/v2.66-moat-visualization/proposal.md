# v2.66 — Moat Visualization Surface

## Problem (the strategic gap, made precise)

The v2.64 "stats & graphs parity" surface answers *"how much AI did I
use?"* — sessions, tokens, streaks, model split, heatmap. That is the
**commodity** half: every single-tool dashboard (claude-mem, Gemini
`/quit`, Codex) already shows it. Matching it is table stakes (the
parity floor), but it is not why anyone keeps Halyard.

The **moat** answers a question no single-tool dashboard *can* draw,
because none of them have a project, a client, a dollar, an
attribution provenance, or an outcome: *"what did AI-assisted work
cost **per client project**, and can I defend it?"* Halyard already
captures every input for that picture — `project`, `cost_usd`,
`attr_method`→confidence (v2.65), `pr_state` (outcomes), human time
(timeclock) — and visualizes **none of it**. The irreplaceable half is
invisible.

## Goal

A first-class **moat visualization surface** on the dashboard:
project/client- and confidence-shaped views that are structurally
impossible in any AI tool's stats screen. All on existing data + the
v2.65 confidence field; same server-rendered inline-SVG primitives as
v2.64 (no JS, offline). Ranks **above** v2.64 — the moat is the reason
to stay; parity is only the price of admission.

Surfaces:

1. **Cost-by-client over time** — stacked area/bars, weeks × **USD**,
   one band per client project. (Gemini draws tokens-by-model; this
   draws spend-by-client — the entire moat in one chart.)
2. **Attribution-confidence trend** — stacked bars per period of
   `timer / mapped / toml / auto / adrift` (v2.65 data visualized):
   graphs *"can I defend this?"* over time.
3. **Per-project billable-evidence card** — human time + AI cost +
   sessions + outcomes (shipped/in-flight/abandoned via `pr_state`) +
   dominant attribution confidence, per client project. The invoice
   appendix, rendered.
4. **Leakage funnel** — adrift $ and session count per remote, each
   with its exact v2.65 `halyard link-repo` fix beside it: moat value
   currently lost and one command from recovered.

## Constraints honored

- **Existing data only.** No new capture. Reuses `project`,
  `cost_usd`, `attribution.attribution_mix`, `pr_state`/`outcome_report`,
  `build_human_time_report`, the doctor adrift grouping.
- **Trust preserved, never overclaimed.** Every $ keeps its cost trust
  label; attribution shows its confidence band; outcomes are labelled
  (shipped/in-flight/abandoned/none) — no ROI claim, no estimate
  presented as fact.
- **Server-rendered, offline, no JS.** Inline SVG/HTML, same primitive
  set as v2.64; v2.42 drag/collapse layout; these panels are
  **primary** (moat is additive *and* above the fold — never demoted
  for commodity stats).
- **Read-only, no silent writes.** The leakage funnel *proposes*
  commands; it never edits `repos.toml`/`halyard.toml`/the log.

## Dependencies & sequencing

- **Best after v2.65** (shipped) — confidence field powers #2/#3.
- **Benefits from v2.62** (cache cost correctness, pending): the $ in
  #1/#3 is only as right as the cost capture. v2.66 does **not** block
  on v2.62, but the dollar figures inherit v2.62's accuracy once it
  lands; note this in the surface ("cost trust" labelling already
  communicates it).
- **Ranks above v2.64.** v2.64 is rescoped to *commodity parity only*;
  v2.66 is the moat counterpart and is the higher priority of the two.

## Non-goals

- ROI / value scoring (Halyard captures spend + outcome state, not
  outcome *value*; that requires user-defined metrics — out of scope).
- Client-side charting libraries (kills offline/zero-build).
- New capture or schema (pure read/visualization layer).

## Out of scope

Per-client PDF/export of the billable-evidence view — that overlaps
the invoice/appendix path (and the gated enterprise attestable
appendix); revisit after this visual surface proves the framing.
