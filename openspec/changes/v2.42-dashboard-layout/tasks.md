# v2.42 — Customizable Dashboard Layout: Tasks

- [x] Add `data-panel` to `_metric` / `_timer_metric` cards
- [x] Add `data-panel` to `_voyage_panel` / `_captains_quarters_panel` /
  `_friends_panel` `<article>`s
- [x] Add `data-panel` to every inline `<article class="panel …">` in
  `_render_state` (12 panels)
- [x] `.layout-reset` control in the topbar (next to theme toggle)
- [x] `_layout_script()` — inject handles/toggles, restore order +
  collapsed from localStorage, drag, collapse, reset; fail-safe
  try/catch; default-order list emitted from the known ids
- [x] CSS: `.is-collapsed`, `.lay-handle`, `.lay-toggle`, `.lay-over`,
  `.lay-dragging`, `.layout-reset`
- [x] Wire `_layout_script()` into the page (next to celebration/easter
  egg scripts)

## Verification

- [x] Python: `tests/test_dashboard_layout.py` — unique `data-panel`
  on all panels+metrics, script + reset control present, default-order
  list matches emitted ids
- [x] Browser (real): drag reorders within container; cross-container
  drag refused; collapse/expand works; order+collapsed survive the 10s
  auto-refresh; reset restores default; forced JS error leaves content
  visible

## Gate

- [x] `pytest` green (1019 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 21)
- [x] PRD reviewed — additive UX on the existing local dashboard; no scope/priority change. Behavior authoritative in `specs/dashboard-layout.md`.
