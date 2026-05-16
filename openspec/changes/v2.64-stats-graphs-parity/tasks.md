# v2.64 — Stats & Graphs Parity Surface: Tasks

Status: **proposed (spec only, not started)**. Best after v2.60–v2.61
(message counts / model attribution feed the stats).

- [ ] `usage.py`: add `total_messages`,
  `message_data_missing_sessions`, `daily_activity`,
  `daily_by_model` to `UsageAnalytics` + `build_usage_analytics`
- [ ] `dashboard.py`: stat-card grid; SVG contribution heatmap;
  upgrade Models tab to stacked per-day series with in/out split + %;
  optional non-authoritative flavour line (gated off reports/invoice)
- [ ] Panels integrate with v2.42 drag/collapse; moat panels stay
  primary (regression guard)
- [ ] `tui/`: headline stats pane (information parity)
- [ ] Tests: `tests/test_v264_stats_graphs_parity.py` (7 cases incl.
  moat-protection + flavour-gating)
- [ ] `docs/PRD-local-activity-dashboard.md` updated
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
