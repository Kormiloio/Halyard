# v2.70 — TUI ↔ web dashboard parity

## Problem & policy change

The Textual TUI is a feature generation behind the web dashboard.
Audit of the two surfaces:

- **TUI has:** session feed, project, watch, captain, voyage, usage
  (v2.64-enriched), budget, model panes + branch/health/help modals.
- **Web dashboard additionally has:** the **moat panel** (v2.65/66 —
  cost-by-client, attribution-confidence trend, per-project billable
  -evidence, leakage funnel) and the **outcomes/leverage panel** (v3.0
  "did it ship?"). The TUI shows none of the moat story.

`openspec/project.md` "Deferred or gated" deliberately defers TUI
widget work (a v2.64 carve-out already exists for `UsagePane`). **The
owner has decided the TUI must be on par with the web dashboard** —
this proposal records that as an explicit, scoped lift of the
TUI-deferral policy (project.md note updated), not silent scope creep.

## Goal

Bring the TUI to **information parity** with the web dashboard's moat
story, reusing the existing data builders — no new data, no new
captured fields.

- **Moat pane (new):** cost-by-client (`moat.cost_by_client`),
  attribution-confidence mix (`attribution.attribution_confidence`),
  leakage rows with the exact one-command fix (`moat.leakage`), and
  per-project billable evidence (human time + AI cost + outcome split
  + confidence). Text-mode equivalents of the web SVG panels — tables
  and compact bars, terminal-appropriate; *information* parity, not
  pixels.
- **Outcomes/leverage pane (new):** the "is AI spend producing
  shipped work?" answer — merged/total PR state %, the same buckets
  the web Leverage panel shows.
- **Shared calc, one source of truth:** the leverage computation
  currently inline in `dashboard._leverage_panel` is factored into a
  reusable function consumed by *both* the web panel and the new TUI
  pane (no duplicated, divergent math).
- Wired into `tui/app.py` with bindings, refreshed by the existing
  watch-and-refresh worker; rendered to each pane's
  `last_rendered_text` so it is unit-testable in the covered layer
  (the v2.64 approach — no Pilot harness needed).

## Constraints honored

- **Reuse, don't rebuild.** `moat.py`, `attribution.py`,
  `build_usage_analytics`, and the factored leverage calc are the
  sources; the TUI only renders.
- **Moat math identical across surfaces.** The shared calc means the
  TUI and web can never disagree on cost-by-client / leverage /
  leakage.
- **Files are the source of truth.** Pure read; no new format.
- **Trust + confidence preserved.** Attribution-confidence and cost
  trust labels render in the TUI panes too, not flattened.
- **Testable layer only.** Panes expose rendered text; no reliance on
  the Textual Pilot harness (consistent with the documented coverage
  policy and the v2.64 carve-out).

## Non-goals

- Pixel/SVG fidelity (terminal can't draw the heatmap/stacked SVG —
  the v2.64 text sparkline + tables stand in; this is info parity).
- The web dashboard's v2.42 drag/collapse customisation in the TUI.
- New metrics or captured data — strictly a presentation lift.

## Out of scope

A full Textual widget test harness (`Pilot`/`run_test()`); the
remaining un-covered TUI widgets stay as-is. This change only adds
panes whose correctness lives in their rendered-text output.
