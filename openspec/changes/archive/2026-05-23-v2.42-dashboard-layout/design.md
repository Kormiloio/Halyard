# v2.42 — Customizable Dashboard Layout: Design

## Stable panel identity (server side)

Every draggable/collapsible element gets a stable `data-panel="<slug>"`:

- The three helper-rendered panels (`_voyage_panel`,
  `_captains_quarters_panel`, `_friends_panel`) take/emit a
  `data-panel` on their root `<article>`.
- Each inline `<article class="panel …">` in `_render_state` gets a
  literal `data-panel` (usage, leverage, sessions, health, adrift,
  wake, timeclock, projects, models, tools, budget, costs).
- `_metric` / `_timer_metric` emit `data-panel` on the `.metric` card
  (timer, human-time, ai-sessions, ai-cost).

Slugs are content-stable identifiers, never user data, so they are safe
in markup and as `localStorage` keys. The set of known ids is also
emitted once into the layout script as the canonical default order.

## Affordances (client side, injected by JS)

To keep the Python markup change minimal and the diff reviewable, the
drag handle and collapse button are **not** added to every
`.panel-head` in Python. Instead the layout script, on
`DOMContentLoaded`, injects into every `[data-panel]`:

- a drag handle (`⠿`) made `draggable`,
- a collapse toggle (`▾` / `▸`) in the header.

CSS:

- `.panel.is-collapsed` / `.metric.is-collapsed` hide all children
  except the header (panel keeps its grid span; only height shrinks),
- `.lay-handle` / `.lay-toggle` small muted controls in the head,
- `.lay-dragging` (source) and `.lay-over` (drop target) affordances,
- a `.layout-reset` button styled like the existing `theme-toggle`.

## Persistence model (`localStorage`)

- `halyard-layout-order-v1` → JSON `{ "<container>": ["id", …] }` where
  container is `grid` or `metrics`. Only ids present are ordered;
  unknown/new ids fall back to their default position so a future
  Halyard release that adds a panel still shows it.
- `halyard-layout-collapsed-v1` → JSON array of collapsed ids.

On load: parse → for each container, stable-sort its `[data-panel]`
children by (saved index, else default index) and re-append in order →
apply `is-collapsed` to listed ids. This runs every refresh; the server
always emits default order and the script restores the user's.

## Drag

HTML5 drag-and-drop. `dragstart` records the source id; `dragover` on a
sibling `[data-panel]` in the **same parent** shows `.lay-over`;
`drop`/`dragend` reorders DOM within that parent and writes
`halyard-layout-order-v1`. Cross-parent drops are ignored (keeps metric
grid vs 12-col panel grid intact).

## Reset

A `.layout-reset` button in the topbar clears both keys and calls
`location.reload()` → server default order, nothing collapsed.

## Resilience

- All layout JS is wrapped so a failure can never blank the dashboard
  (try/catch around restore; the page already rendered server-side).
- Unknown saved ids are ignored; missing ids use default order — forward
  compatible with added/removed panels.
- No effect on no-JS or the auto-refresh cadence.

## Test strategy

Python (`tests/test_dashboard_layout.py`): the rendered HTML has a
`data-panel` on every panel and metric, the ids are unique, the layout
`<script>` and `.layout-reset` control are present, and the default-order
list in the script matches the emitted panels. Behavioral
drag/collapse/persistence is verified manually in a real browser
(documented in tasks.md) since it is client-side JS — Python tests
assert structure, not DnD.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
