# v2.64 — Stats & Graphs Parity Surface: Design

## Data layer (one new aggregate)

`usage.py` `UsageAnalytics` already carries: `sessions`,
`total_input_tokens`, `total_output_tokens`, `total_cache_*`,
`active_days`, `current_streak_days`, `longest_streak_days`,
`peak_hour`, `favorite_model`, `by_model` (per-model in/out/cache),
`by_tool`.

Add:

- `total_messages: int` — sum of `user_message_count +
  assistant_message_count` over sessions where present (missing →
  contributes 0 to the sum but is *not* a fabricated per-session 0;
  the existing `token_data_missing_sessions` pattern is the model to
  mirror with a `message_data_missing_sessions: int`).
- `daily_activity: list[DayCell]` — per-day `(date, sessions, tokens)`
  for the selected range, for the heatmap.
- `daily_by_model: list[DayModel]` — per-day per-model
  `(date, model, input, output)` for the stacked time series.

All derived from the already-selected session set in
`build_usage_analytics`; no new capture, no new I/O.

## Render layer (inline SVG/HTML, no JS)

`dashboard.py`, within the existing `usage` panel + as additive
panels (draggable/collapsible per v2.42):

1. **Stat cards** — a grid mirroring the single-tool layout:
   sessions · messages · total tokens · active days · current streak ·
   longest streak · peak hour · favorite model. Pure HTML, each card
   carries its trust treatment where relevant.
2. **Contribution heatmap** — an SVG/CSS grid of week-columns ×
   weekday-rows, cell fill bucketed by that day's activity
   (`daily_activity`). 5 intensity buckets; legend; respects the
   7d/30d/all range control.
3. **Models time series** — upgrade the "Models" tab to a per-day
   **stacked** bar (SVG `<rect>`s), one stack segment per model,
   plus a legend showing per-model `in / out` token split and **%
   share** (already computable from `by_model`).
4. **Flavour line** — optional, single line, clearly non-authoritative
   (e.g. "≈ N× <reference>"), gated so it never appears on
   trust-bearing surfaces (reports, invoice).

No charting dependency; all output is static markup so it works
offline and in the existing server-rendered model.

## TUI parity (proportional)

`tui/` — the headline numbers (sessions, messages, tokens, active
days, streaks, peak hour, favorite model) as a stats pane. The
heatmap/stacked-chart are out of scope for the TUI (terminal
constraints); a compact per-model sparkline-style row is acceptable if
cheap, else text figures only. Parity of *information*, not pixels.

## Moat-protection rule

The parity surface is **additive**. The cost and project/attribution
panels remain primary and above-the-fold; no existing moat surface is
removed or demoted to fit stats. Reviewer/QA check: a screenshot of
the dashboard still shows cost + project before any vanity stat.

## Tests (`tests/test_v264_stats_graphs_parity.py`)

1. `total_messages` / `message_data_missing_sessions` correct over a
   mixed fixture (some sessions lack message counts).
2. `daily_activity` / `daily_by_model` bucketing correct for a known
   multi-day, multi-model fixture; respects range filter.
3. Heatmap renderer emits the right cell count and intensity buckets
   for a known activity vector (assert structure, not pixels).
4. Models time series: stacked segments per day sum to per-day totals;
   per-model % share sums to ~100.
5. Flavour line absent from report/invoice surfaces; present only on
   the dashboard stats panel.
6. Moat-protection: rendered dashboard still contains the cost and
   project panels (regression guard against demoting the moat).
7. TUI stats pane shows the headline figures.

## Docs

`docs/PRD-local-activity-dashboard.md`: add the Stats parity surface
and the **parity-floor principle** (also added to
`current-direction.md` Governing Principles in this batch).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Feature changeset — full spec.
