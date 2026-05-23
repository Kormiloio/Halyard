# v2.66 — Moat Visualization Surface: Tasks

Status: **complete (1192 tests passing)**.

- [x] `src/halyard/moat.py`: `cost_by_client`, `confidence_trend`,
  `project_evidence`, `leakage` (existing data + v2.65
  `attribution_confidence`; outcomes via `pr_state`; human time via
  `build_human_time_report`)
- [x] `link_repo_command` is the single shared remediation builder;
  `doctor._link_repo_command` delegates to it (one source of truth)
- [x] `dashboard.py` `_moat_panel`: billable-evidence table,
  cost-by-client bars, leakage funnel; rendered **before** the
  commodity Usage panel (ordering invariant test-enforced); registered
  in the v2.42 panel layout
- [x] Tests: `tests/test_v266_moat_visualization.py` (7 cases incl.
  moat-before-commodity invariant + leakage-no-write + single-source
  builder); `test_dashboard_layout` panel registry updated
- [x] Roadmap entry status in `openspec/project.md` (item 43)
- [x] `docs/PRD-local-activity-dashboard.md` + `current-direction.md`
  note the moat surface ranks above commodity parity

Deferred (tracked, not silently dropped):
- [ ] TUI per-project `$ · sessions · confidence` table — the TUI is
  a documented secondary surface (see roadmap "Deferred or gated";
  widget harness deferral). Dashboard + data layer ship now; TUI
  column is a follow-up so a fragile Textual change isn't rushed.

## Gate
- [x] `pytest` green (1192 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
