# v5.13 — Design

## Today

`_render_state(state, usage_range, usage_tab)` builds the `context` dict
that feeds `dashboard.html.j2`. Two keys drive the Wake panel:

```python
"wake_month":    _e(now.strftime("%B %Y")),
"trail_heatmap": _trail_heatmap_html(report.sessions, now),
```

`now` is `state.generated_at` (i.e. `datetime.now()` at request time).
`report.sessions` is built by `build_ai_report(project_dir, now=now)`,
which filters to `start.year == now.year and start.month == now.month`
([reports.py:138-144](../../../src/halyard/reports.py)). So changing the
datetime we pass downstream changes both the label *and* the heatmap data
in lockstep — exactly what we want.

## Approach

1. **Parse the param** in the FastAPI/Starlette route handler that calls
   `_render_state`. Accept `month=YYYY-MM`; on parse failure or a
   future-dated month, ignore it (treat as "current"). Months earlier than
   the earliest captured session also fall back — there's nothing to show
   and we don't want broken links.

2. **Thread a `wake_period: datetime` through `_render_state`** as a new
   keyword arg defaulting to `None` (= use `state.generated_at`). When
   non-None, use it for the two Wake-panel context keys and for filtering
   `report.sessions` to that month.

   The cleanest seam: build a `wake_sessions` list inside `_render_state`
   by re-filtering `state.all_sessions` to `wake_period`'s month when
   `wake_period` differs from `state.generated_at`. The default path
   keeps the existing `report.sessions` reference (same object, zero
   behaviour change for the default month).

3. **Render the nav links** in `dashboard.html.j2`. The template already
   gets `wake_month` as pre-rendered HTML. Replace it with three
   context keys: `wake_prev_href`, `wake_month` (now a plain string), and
   `wake_next_href` (empty string when viewing current month → template
   renders no `›`).

   Links preserve other query params so `?range=7d&tab=models` survives a
   month step. Build them with `urllib.parse.urlencode` from the active
   `usage_range`/`usage_tab`.

## Trade-offs considered

- **Why a query param, not a stateful cookie?** Local-first, plain-text
  ethos: the URL *is* the state. Bookmarkable, shareable across the user's
  own tabs, survives reloads without writing anything to disk.
- **Why not also let `?month=` move the Sessions / Adrift / Usage panels?**
  Wake is the only month-labelled panel; the others have their own range
  controls (`?range=`). Bundling them in one param would create surprising
  cross-panel coupling and force a much bigger UI rethink. Keep it scoped.
- **Why hide `›` instead of disabling it?** Disabled links still appear
  clickable in some browsers when CSS is unstyled (offline-first matters
  here). A missing element can't be clicked.
- **Why fall back silently on bad input instead of 400?** This is a
  local-only dashboard. A 400 page hides the rest of the dashboard
  data; silently snapping to "current month" lets the user keep
  working and the bad URL self-corrects on the next nav click.

## Rejected

- Adding a `<select>` month-picker dropdown. Bigger surface, JS-heavy on
  a server-rendered page, and the project's `dashboard.css` already styles
  pill-link nav (used by `_range_control`); reusing that pattern keeps
  visual weight consistent with the rest of the Bridge.
- Persisting `wake_month` in `~/.halyard/state` or similar. Nothing in the
  rest of the dashboard does this; introducing it for one panel is
  inconsistent and reaches for state we don't need.

## Schema / format impact

None. No new files, no migrations, no on-disk format changes.

## Files touched

- `src/halyard/dashboard.py` — route handler param, `_render_state`
  signature, Wake context keys, small URL-builder helper.
- `src/halyard/templates/dashboard.html.j2` — Wake panel head: render
  `‹` / `›` links around the month label.
- `tests/test_dashboard_*.py` — one new test asserting the Wake panel
  scopes correctly when `?month=` is passed.
