# v2.64 — Stats & Graphs Parity Surface: Design

## Phase 0 — Grounding audit (COMPLETE 2026-05-16)

Audited `usage.py` / `dashboard.py` / `tui/` before code. Three
findings refine the scope:

1. **`daily_activity` is redundant — drop it.** `UsageAnalytics.daily:
   list[DailyUsageBucket]` already exists and is zero-filled across the
   full selected range with per-day `sessions`, token split, `cost`,
   `has_missing_token_data`, and `model_tokens: dict[str,int]`. The
   contribution heatmap renders directly from `usage.daily`; no new
   `DayCell` type.

2. **`daily_by_model` is partially redundant but the in/out split is
   real.** `DailyUsageBucket.model_tokens` already gives per-day
   per-model *total* tokens — but the existing `_daily_model_chart`
   (`dashboard.py:1427`) **does not use it**; it spreads each model's
   window-wide total proportionally across days (a documented
   approximation, accurate only when one model ran per day). v2.64
   should (a) make the stacked chart use the *real* `day.model_tokens`,
   and (b) add per-day-per-model **input/output** to `DailyUsageBucket`
   (extend `_daily_bucket` to also accumulate `model_io: dict[str,
   tuple[int,int]]`) for the in/out split the spec requires. This is
   the only substantive data-layer change beyond `total_messages`.

3. **Reusable render scaffolding exists.** Headline cards → the
   `metric metric-{tone}` article idiom (`:1226`). Heatmap → structural
   template in `_trail_heatmap_html` (`:2305`), but that one is
   month-scoped + attribution-coloured (wake panel); v2.64 needs a
   *new* range-aware activity-intensity heatmap (5 buckets) — template,
   not reuse. Models tab already has chart+legend+table to upgrade in
   place; `ModelUsageBucket` already carries `token_share`/`cost_share`
   /`session_share` so "% share" needs no new math.

### Scope conflict to resolve before building — TUI parity vs. the
TUI-deferral policy

`openspec/project.md` "Deferred or gated" states TUI widget/app
coverage is a *conscious deferral* (only `tui/store.py` state is
covered; widgets need the Pilot harness — high effort, low return
while the TUI is secondary). `tui/store.py` currently has **zero**
usage/analytics wiring. The spec's "TUI information parity" requirement
+ test case 7 directly tension with that policy. **Resolution (user
decision 2026-05-16): build a full Textual stats widget** — an
explicit, owner-approved deviation from the TUI-deferral policy
(project.md permits deviations with explicit justification; the
justification here is that the parity surface is the strategic
first-impression and the owner wants full TUI parity, not just
information parity). Scope: a `stats` summary on the covered
`tui/store.py` layer (unit-tested) **and** a Textual stats widget
wired into the app. The project.md deferral note is updated to record
this carve-out.

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
