# v2.64 — Stats & Graphs Parity Surface: Tasks

Status: **COMPLETE 2026-05-16.** Phase 0 audit rescoped the data
layer (`daily_activity` redundant — `UsageAnalytics.daily` already
exists; only `total_messages` + per-day-per-model in/out genuinely
missing). TUI scope: full widget parity per owner decision (carve-out
from the TUI-deferral policy, recorded in design.md + project.md).

- [x] `usage.py`: `total_messages` + `message_data_missing_sessions`
  on `UsageSummary`; `DailyUsageBucket.model_io` (real per-day
  per-model in/out, multi-model aware). `daily_activity`/`daily_by_model`
  not added — `usage.daily` already serves the heatmap; `model_io`
  serves the chart
- [x] `dashboard.py`: 8-figure headline grid (+ messages, active days,
  split streaks; cost retained labelled `· moat`); range-aware
  heatmap + 5-bucket legend; Models chart now uses REAL `model_io`
  (was a window-wide approximation) + legend in/out + % share;
  dashboard-only flavour line (`_usage_flavour_line`, never
  report/invoice)
- [x] Panels keep existing `data-panel` ids (v2.42 drag/collapse);
  moat panels intact — executable regression guard added
- [x] `tui/`: `UsagePane` enriched to full headline parity incl.
  messages + message-missing trust (no redundant second widget)
- [x] Tests: `tests/test_v264_stats_graphs_parity.py` (8 cases incl.
  moat-protection + flavour-gating + TUI parity)
- [x] `docs/PRD-local-activity-dashboard.md` + `current-direction.md`
  updated
- [x] Roadmap entry in `openspec/project.md` + TUI carve-out note

## Gate
- [x] `pytest` green
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
