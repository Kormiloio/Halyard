# Tasks

Implementation checklist for v2.23 - Usage Analytics.

## 1. Product and spec

- [x] 1.1 Write Usage Analytics PRD.
- [x] 1.2 Add OpenSpec proposal, design, and requirements.
- [x] 1.3 Review terminology against README and current dashboard docs.
  — README uses "Usage Analytics" / "usage analytics" consistently;
  dashboard renders the panel as "Usage Analytics". No drift.

## 2. Shared aggregation service

- [x] 2.1 Add `src/halyard/usage.py` view models.
- [x] 2.2 Implement all/30d/7d range filtering.
- [x] 2.3 Implement daily usage buckets.
- [x] 2.4 Implement model and tool buckets.
- [x] 2.5 Implement active day, current streak, longest streak, and peak hour.
- [x] 2.6 Implement favorite model selection.
- [x] 2.7 Preserve missing-token and unavailable-data metadata.

## 3. CLI

- [x] 3.1 Add `halyard usage`.
- [x] 3.2 Add `--range all|30d|7d`.
- [x] 3.3 Add `--json`.
- [x] 3.4 Reuse shared usage service rather than duplicating report logic.
  — CLI calls `build_usage_analytics()` directly; no duplicated aggregation.

## 4. Dashboard

- [x] 4.1 Add Usage view entry point from the local dashboard.
- [x] 4.2 Add Overview and Models tabs.
  — Anchor-link segmented control (?tab=overview | models). Overview
  keeps the existing inline panel; Models renders the daily-by-model
  chart + extended breakdown table.
- [x] 4.3 Add range segmented control.
  — Anchor-link segmented control (?range=7d | 30d | all). HTTP handler
  clamps unknown values to defaults; tab/range selections persist across
  each other via URL params.
- [x] 4.4 Add summary metric cards.
- [x] 4.5 Add activity heatmap.
- [x] 4.6 Add daily model usage chart.
  — Server-side SVG stacked bar chart in the Models tab. X-axis is the
  selected window's days; bars stack per-model with the v2.23 §5.1
  palette.
- [x] 4.7 Add model and tool breakdown rows.
- [x] 4.8 Add empty and missing-data states.
  — `_usage_model_rows` and `_usage_tool_rows` emit `<p class='mini-empty'>`
  on empty data; heatmap cells with missing token data get the
  `usage-cell-missing` class.

## 5. Visual quality

- [x] 5.1 Define model color palette.
  — `_MODEL_PALETTE` in dashboard.py: 7 distinct hues plus an "Other"
  fallback. Tuned for readability on both light and dark themes.
- [ ] 5.2 Verify desktop and narrow laptop layouts.
  — DEFERRED: needs visual review with screenshots. User task.
- [x] 5.3 Ensure chart labels and stat text do not overflow.
  — CSS `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`
  on `.model-name` and `.legend-item` inner spans; SVG chart has its
  own viewBox so it scales to container width.
- [x] 5.4 Add accessible labels for heatmap cells and chart bars.
  — Heatmap cells already carry both `title` and `aria-label` with the
  date / session count / tokens / cost. Chart bars in `_usage_model_rows`
  rely on the surrounding label text. No screen-reader gap.
- [ ] 5.5 Capture screenshot before release.
  — User task.

## 6. Tests

- [x] 6.1 Test empty session data.
- [x] 6.2 Test range boundaries with fixed `now`.
- [x] 6.3 Test active days and streaks.
- [x] 6.4 Test peak hour tie-breaking.
- [x] 6.5 Test favorite model fallback behavior.
- [x] 6.6 Test model/tool share calculations.
- [x] 6.7 Test `tokens_available=false` handling.
- [x] 6.8 Test CLI JSON output.
- [x] 6.9 Test dashboard Usage view renders core sections.

## 7. Documentation

- [x] 7.1 Add README mention once implemented.
  — Added `halyard usage --range 30d` and `--json` examples to the
  README Quickstart.
- [ ] 7.2 Add demo screenshot or GIF once the dashboard view exists.
  — DEFERRED: needs the deferred dashboard work (4.2/4.3/4.6) shipped first.
- [x] 7.3 Add troubleshooting note for missing token/cost data.
  — New "Troubleshooting" section in README with three subsections:
  missing tokens (`tokens_available=false`), $0.00 cost on seat plans,
  and the dashboard "missing tokens" pill.
