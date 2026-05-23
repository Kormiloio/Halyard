# v2.64 — Stats & Graphs Parity Surface

## Problem (and the strategic stake)

Single-tool stat dashboards (claude-mem-style Overview, Gemini `/quit`,
Codex usage view) show, at a glance: sessions, messages, total tokens,
active days, current/longest streak, peak hour, favorite model, a
contribution heatmap, and per-day per-model token bars with an in/out
split.

Halyard's **data is already there** — `UsageAnalytics` computes
sessions, active days, current/longest streak, peak hour, favorite
model, and per-model token buckets (in/out/cache). What's missing is
**the visualization**: the heatmap, the per-day per-model time series,
the in/out split, the headline stat cards, and one missing aggregate
(message totals).

**Why this is strategic, not cosmetic.** Halyard's moat is cost,
project/client attribution, cross-tool unification, and outcome
linkage — things no single-tool dashboard has. But a developer's
first reaction to Halyard is a *comparison* to the stat screen they
already see in their tool. If Halyard shows *less* than that screen,
the reaction is **"I already get this from my AI tool — Halyard
doesn't add enough for me to care,"** and they never reach the moat.
Parity on table-stakes stats is the price of admission for the moat to
land. This change buys that admission cheaply because the metrics
already exist.

## Goal

A polished **Stats** parity surface on the dashboard (and proportional
TUI parity) that meets or exceeds what the single-tool screens show,
built almost entirely on existing `UsageAnalytics` data.

- Headline stat cards: sessions, **messages** (new aggregate), total
  tokens, active days, current streak, longest streak, peak hour,
  favorite model.
- **Contribution heatmap** (calendar grid, activity-weighted).
- **Per-day per-model stacked time series** with **input/output
  split** and per-model **% share** (the "Models" view, upgraded).
- Optional flavour line (e.g. token-volume comparison) — clearly
  labelled, off the trust path.
- Every figure keeps its **trust label**; moat columns (cost,
  project) stay first-class and visible — parity *plus* the moat, not
  parity *instead of* it.

## Constraints honored

- **Mostly presentation.** Only one new metric (message totals);
  everything else renders existing `UsageAnalytics`.
- **Server-rendered, no JS framework.** Charts are inline SVG/HTML,
  consistent with the existing dashboard architecture and the v2.42
  customizable-panel layout (new panels are draggable/collapsible like
  the rest).
- **Files are the source of truth.** Pure read view; no writes.
- **Moat stays primary.** Cost and attribution are never dropped to
  make room for vanity stats; the parity surface is additive.

## Non-goals

- Client-side interactivity / charting libraries (keeps the
  zero-build, offline, server-rendered model).
- New capture (message *counts* per session already exist from the
  collector work; this only aggregates them).
- Gamification beyond a single optional, clearly-labelled flavour line.

## Out of scope

A configurable/custom dashboard builder. This delivers a fixed,
well-designed parity surface; bespoke layouts remain the v2.42
drag/collapse mechanism.
