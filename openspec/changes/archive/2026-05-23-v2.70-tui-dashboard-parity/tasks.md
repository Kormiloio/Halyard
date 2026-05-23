# v2.70 — TUI ↔ web dashboard parity: Tasks

Status: **COMPLETE 2026-05-16 (1230 tests passing).** Render +
small-refactor lift, no new data: all builders (`moat.py`,
`attribution.py`, report/usage) already existed; the only inline math
(leverage % + buckets in `dashboard._leverage_panel`) was factored
into the shared `leverage.summarize` consumed by both web + TUI.

- [x] `leverage.py`: `LeverageSummary` + `summarize(sessions, now)`;
  refactored `dashboard._leverage_panel` onto it (behaviour-identical,
  dashboard leverage golden unchanged — 7 leverage tests still green).
  `LeverageSummary` carries the full bucket set (total/merged/open_/
  closed/none/unsynced/pct), a superset of the design sketch, so the
  refactor stays byte-identical
- [x] `tui/widgets/moat_pane.py`: `MoatPane` — cost-by-client (view
  totals + bar), attribution-confidence mix (reuses
  `format_attribution_mix`), per-project billable evidence, leakage
  rows + exact `link-repo` fix; all model/remote/client strings
  `rich.markup.escape`d; `last_rendered_text`
- [x] `tui/widgets/leverage_pane.py`: `LeveragePane` — shipped % +
  merged/open/closed/no-PR/unsynced from `leverage.summarize`
- [x] `tui/app.py`: compose yields both panes, `refresh_views` wires
  them with the filtered set + project_dir + generated_at, `o`
  scroll-to-moat binding; reuses the existing watch-and-refresh worker
- [x] Tests: `tests/test_v270_tui_parity.py` (7 cases: moat render +
  no-markup-leak, leakage+exact-fix, leverage buckets, web↔pane
  single-source parity, empty state, confidence labels preserved, app
  -wiring smoke via run_test)
- [x] `openspec/project.md` "Deferred or gated": v2.70 TUI-deferral
  lift recorded (generalises the v2.64 carve-out; Pilot-harness
  deferral still stands for untouched legacy widgets)
- [x] `docs/PRD-local-activity-dashboard.md`: TUI information-parity
  section added (mirrors moat + leverage; shared math)
- [x] Roadmap entry in `openspec/project.md` (status → complete)

Deviation from design: the wiring smoke uses `run_test()` (matching
the existing `UsagePane` smoke in `test_tui.py`) — pane *correctness*
stays Pilot-free as specced; only the one app-composition smoke uses
the harness, consistent with the repo's established pattern.

## Gate
- [x] `pytest` green (1230 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
