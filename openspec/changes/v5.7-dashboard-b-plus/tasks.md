# Tasks — v5.7 Dashboard B+

- [x] SVG helpers: `_svg_donut`, `_svg_area`, `_svg_stacked_bar`; `_norm_project`.
- [x] Overview panels (`data-tab="overview"`): KPI strip, cost donut (cost-only),
      model-mix donut, tokens trend, activity heatmap, top-projects, outcomes.
- [x] Tab bar (Overview/Money/Sessions/Voyage/Health/All); panel→tab map in
      `_tabs_script` (no per-panel markup change); client-side show/hide,
      persisted, re-applied after the v5.6 refresh via `HalyardApplyTabs`.
- [x] `_layout_script`: per-panel hide (✕) + `▦ panels` manage menu to restore
      (persisted `halyard-removed-v1`).
- [~] Sort affordance: **already provided by the v2.73 engine** (renders `⇅` on
      sortable columns). Browser check showed a first-cut blanket `::after ↕`
      double-glyphed sortable headers and falsely marked non-sortable ones —
      removed it; kept only `cursor:pointer`. No new indicator needed.
- [x] Apply `_norm_project` to project grouping for the Overview charts.
- [x] Existing dashboard suite stays green (107); add v5.7 tests (+7).
- [x] ruff + mypy clean; full suite green (1505 passed).
- [x] Browser-verified: tabs filter panels, Overview charts render, real Voyage
      icons preserved, on/off + manage menu persist, sort works (`⇅`, no
      double-glyph), no console errors, attribution merged.
- [ ] Roadmap entry 81; delete prototype + `dash-proto` launch config.
