# v2.66 — Moat Visualization Surface: Tasks

Status: **proposed (spec only, not started)**. Ranks **above** v2.64.
Best after v2.65 (shipped); $ accuracy inherits v2.62 when it lands.

- [ ] `src/halyard/moat.py`: `cost_by_client`, `confidence_trend`,
  `project_evidence`, `leakage` rollups (existing data + v2.65
  `attribution_confidence`; outcomes via `pr_state`; human time via
  `build_human_time_report`)
- [ ] Factor the v2.65 `link-repo` remediation string into one shared
  builder used by both `doctor` and `moat.leakage`
- [ ] `dashboard.py`: 4 inline-SVG/HTML panels (cost-by-client,
  confidence trend, billable-evidence cards, leakage funnel); v2.42
  layout; ordered **before** the v2.64 commodity stats panel
- [ ] TUI: compact per-project "$ · sessions · confidence" table
- [ ] Tests: `tests/test_v266_moat_visualization.py` (8 cases incl.
  moat-ordering invariant + leakage-no-write + single-source builder)
- [ ] `docs/PRD-local-activity-dashboard.md` + `current-direction.md`
  updated (moat surface ranks above commodity parity)
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
