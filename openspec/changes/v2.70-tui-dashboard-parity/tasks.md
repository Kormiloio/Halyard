# v2.70 — TUI ↔ web dashboard parity: Tasks

Status: **proposed (spec only, not started).** Owner decision: TUI
must be on par with the web dashboard. Audit: all data builders
(`moat.py`, `attribution.py`, `build_ai_report`,
`build_usage_analytics`) already exist — the leverage math is the
only thing inline (in `dashboard._leverage_panel`) and gets factored
into a shared function. This is a render + small-refactor lift, not
new data.

- [ ] `leverage.py`: `LeverageSummary` + `summarize(sessions, now)`;
  refactor `dashboard._leverage_panel` onto it (behaviour-identical,
  dashboard leverage golden unchanged)
- [ ] `tui/widgets/moat_pane.py`: `MoatPane` — cost-by-client,
  attribution-confidence mix, leakage + fix, per-project billable
  evidence; escaped text; `last_rendered_text`
- [ ] `tui/widgets/leverage_pane.py`: `LeveragePane` — shipped % +
  buckets from `leverage.summarize`
- [ ] `tui/app.py`: compose + refresh_views wiring + a focus/scroll
  binding; reuse the watch-and-refresh worker
- [ ] Tests: `tests/test_v270_tui_parity.py` (6 cases incl. shared
  -calc parity, escape proof, empty state, trust labels, app wiring)
- [ ] `openspec/project.md` "Deferred or gated": record the v2.70
  TUI-deferral lift (generalises the v2.64 carve-out)
- [ ] `docs/PRD-local-activity-dashboard.md`: TUI mirrors moat +
  leverage (information parity)
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
