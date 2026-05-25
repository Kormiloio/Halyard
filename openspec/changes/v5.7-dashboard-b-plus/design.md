# Design — v5.7 Dashboard B+

## Guiding constraint: keep everything, break nothing

Tabs are **client-side visibility**, not server-side routing. `_render_state`
emits every panel as today, each tagged `data-tab="<group>"`; a script shows
only the active tab's panels. Because all panels remain in the rendered HTML,
the existing dashboard test suite (which asserts panel presence / `data-panel`
ids) keeps passing, and the real panel renderers (Captain's Quarters, Friends
of the Sea, Moat, …) render with all their icons unchanged. This also composes
with the v5.6 partial refresh (the swap re-runs the tab + layout re-init).

## Charts (inline SVG, no deps)

New helpers in `dashboard.py`, mirroring the prototype that won:
- `_svg_donut(segments, …)` — stroke-dasharray arcs + centre label.
- `_svg_area(values, …)` — area+line trend.
- `_svg_stacked_bar(parts)` — single part-to-whole bar.
- heatmap reuses the existing `_activity_heatmap` / trail.

Overview panels (new `data-panel` ids, `data-tab="overview"`): `ov-kpis`,
`ov-cost` (cost donut, **cost only** — never fall back to tokens), `ov-models`
(token mix), `ov-trend`, `ov-activity`, `ov-projects`, `ov-outcomes`. Cost donut
uses `sum_spend`; model/token data from `UsageAnalytics`.

## Tabs

Tab bar in the template (server-rendered buttons). Groups:
- **Overview** — the new chart panels.
- **Money** — Moat, Costs, Budget, Projects.
- **Sessions** — Recent Sessions, Adrift, Collisions, Tools/Surfaces, Timeclock.
- **Voyage** — Captain's Quarters, Current Voyage, Friends of the Sea, Wake.
- **Health** — Collector State, Usage Analytics, Models, Leverage/Outcomes.
- **All** — everything (today's flat view), for power users.

`data-tab` added to each `<article>`. A script reads the active tab from
`localStorage` (default `overview`), toggles a `.tab-hidden` class on panels
whose `data-tab` ≠ active (the **All** tab clears all hiding), and is re-applied
after a partial-refresh swap. No-JS: everything shows (graceful).

## On/off + manage + sort glyph

- `_layout_script`: add a hide (✕) button per panel → `.is-removed` + persist;
  a "panels" menu (from the topbar) lists panels with checkboxes to restore.
  Distinct from collapse (which only hides the body).
- Sort glyph: CSS `table[data-sortable] th::after{content:" ↕"}` + active-column
  styling reusing the v2.73 `data-asc`/sorted state.

## Attribution normalization

`_norm_project(slug)` — lowercase, unify `/`→`:`, small alias map — applied
where the dashboard groups cost by project for the Overview charts (and the
projects panel). History/log untouched; this is a read-time display merge.
Documented as a partial fix; the real remote→slug map is a follow-up.

## Test strategy

Existing suite stays green (panels still present). New tests: Overview panels
render with the SVG charts; tab bar + `data-tab` on every panel; hide/manage
markup; `↕` on sortable headers; `_norm_project` merges the known dupes; cost
donut never shows token magnitudes. Browser-verify tab switching, on/off, sort.
