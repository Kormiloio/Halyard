# v5.7 — Dashboard "B+": tabbed overview, richer charts, panel on/off

## Why

The Bridge feels overloaded — ~18 equally-weighted panels with the same numbers
repeated. After prototyping three directions (`prototypes/dashboard_redesign.py`,
see its NOTES.md), the owner picked **B+**: a tabbed dashboard with a calm
**Overview** built from a few hero visuals, every existing panel preserved, and
the lost controls (per-panel on/off, visible column sort) restored.

## What changes

1. **Overview tab (new).** Server-rendered inline-SVG visuals (no CDN/JS lib —
   offline-first): a cost donut ("where the money went", cost-only), a
   model-mix donut (tokens), a tokens-over-time trend, the activity heatmap, a
   top-projects-by-cost bar set, an outcomes stacked bar, and a compact KPI
   strip. These are *new* panels (own `data-panel` ids), not duplicates.
2. **Tabs.** A tab bar — Overview · Money · Sessions · Voyage · Health · All —
   tags every panel with `data-tab` and shows only the active tab's panels.
   Crucially this is **client-side show/hide**: every panel stays in the DOM
   (real renderers, all icons — creature/passport/medals/ranks — intact), so the
   server output and existing tests are preserved; only visibility changes.
   Active tab persists in `localStorage` and survives the v5.6 partial refresh.
3. **Per-panel on/off + manage menu.** `_layout_script` gains a hide (✕) control
   per panel and a "panels" menu to switch hidden ones back on (persisted),
   alongside the existing collapse/drag.
4. **Sort affordance — already present.** The v2.73 sort engine already renders
   a `⇅` indicator on sortable columns. Browser verification confirmed this, so
   no new glyph was added (a first-cut blanket `::after ↕` was removed — it
   double-glyphed sortable headers and falsely marked non-sortable ones).
5. **Attribution normalization.** Project slugs that differ only by
   separator/casing (`kormilo/halyard` vs `kormilo:halyard`) merge so the cost
   donut / top-projects stop splitting one project. Scoped to the dashboard's
   grouping here; a full remote→slug map is a separate follow-up.

## Impact

- Affected: `src/halyard/dashboard.py` (new chart helpers + Overview panels +
  tab/hide/sort scripts), `templates/dashboard.html.j2` (tab bar + grouping),
  `templates/dashboard.css` (tabs, charts, sort glyph).
- **Preserves everything:** no panel removed; all stay in the DOM, grouped by
  tab. Sort + collapse + drag (v2.73 / earlier) retained; on/off added.
- Offline-first: all charts are hand-rendered inline SVG, no new dependency.
- Out of scope: a production remote→slug attribution map (follow-up); the
  prototype is deleted on completion.
