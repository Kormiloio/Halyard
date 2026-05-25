# Tasks — v5.6 Dashboard templating + external CSS + HTMX

## Phase #2 — external CSS
- [x] Move `_CSS` verbatim → `templates/dashboard.css` (437 lines).
- [x] Add cached `_load_css()`; `_render_state` passes `css=_load_css()`.
- [x] Dashboard suite green (107 tests; CSS-substring tests unchanged).

## Phase #1 — panel templates
- [x] `templates/panels/_macros.html.j2` `data_table` macro (owns
      table/thead/tbody/tr/td + the `_stbl` sort attributes).
- [x] Shared cached `_env()`; `_panel_macros()` renders macros from Python.
- [x] Convert the 7 repetitive table builders to context-dict + macro:
      models, tools, bucket/projects, collisions, time, unattributed, sessions.
- [~] Logic-heavy panels (moat, voyage, captain's quarters, costs, leverage,
      usage) **intentionally stay in Python** — Jinja is poor at their
      conditional logic; converting adds risk for little gain (design.md).
- [x] Dashboard suite green after each builder (107 tests).

## Phase #3 — native partial refresh (HTMX rejected: offline-first)
- [x] Decision: HTMX vendoring needs the file offline / CDN breaks offline-first
      → native partial refresh (zero dep). Recorded in design.md.
- [x] `id="metrics"` + `id="grid"` on the two refreshable regions.
- [x] `_layout_script`: expose idempotent `window.HalyardApplyLayout`;
      `addControls` guarded against double-wiring.
- [x] `_refresh_script` (replaces `_hub_events_script`): 10s timer + Hub SSE
      swap the metrics/grid region innerHTML in place, then re-run
      `HalyardBootTables` + `HalyardApplyLayout`.
- [x] Drop the full-page `<meta refresh>`.
- [x] Update `test_dashboard_scroll_preserve` (no meta refresh; partial swap) +
      `test_v43_realtime_dashboard` (swap idiom).
- [x] Browser-verified: window probe persists (no reload), grid innerHTML
      swapped, layout controls + collapse state survive the swap, no console
      errors.

## Wrap
- [x] ruff + ruff format + mypy clean; full suite green (1498 passed).
- [x] Roadmap entry 80 in `openspec/project.md`.
