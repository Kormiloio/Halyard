# Design — v5.6 Dashboard templating + external CSS + HTMX

## Phase order

`#2 (CSS) → #1 (panels) → #3 (HTMX)`. Each phase keeps the full dashboard test
suite green before the next starts; #3 is browser-verified via the preview
tools because it changes runtime refresh behaviour.

## #2 External CSS

- `_CSS = """…"""` (≈440 lines, module tail) moves verbatim to
  `templates/dashboard.css`.
- `@lru_cache _load_css()` reads `_TEMPLATE_DIR / "dashboard.css"` once; the
  `_render_state` context passes `css=_load_css()`.
- Output identical (still inlined in `<style>`), so the CSS-substring
  assertions (`.lay-handle`, `.is-collapsed`, `.metric > .lay-controls …`)
  keep passing. The only win is tooling + a smaller module — no behaviour
  change, lowest risk, done first.

## #1 Panel templates

- New `templates/panels/` holds one `.j2` per panel/table.
- Builders keep all *computation* (number/trust formatting, bar widths,
  conditional classes) in Python and pass a context (lists of row dicts) to a
  template that owns the markup. Jinja is poor at logic, so logic stays in
  Python; only HTML structure moves.
- The repetitive **table** builders go first (`_sessions_table`,
  `_bucket_table`, `_model_table`, `_tool_table`, `_time_table`,
  `_unattributed_table`, the usage row helpers) — they are pure
  loop-over-rows and the biggest mechanical win. Logic-heavy panels
  (`_moat_panel`, `_voyage_panel`, `_captains_quarters_panel`, `_costs_panel`)
  follow, each verified against its existing tests.
- Escaping: templates run under the existing `autoescape=True` env; values
  already escaped via `_e`/pre-rendered HTML are marked `|safe`, matching v5.4.

## #3 Native partial refresh (HTMX rejected)

**Why not HTMX.** Vendoring `htmx.min.js` would commit a ~50 KB file to the
repo, and a CDN `<script src>` would break the offline-first non-negotiable
(auto-update silently dies without internet). The existing SSE script already
does client-side fragment swaps, so the missing piece is only the periodic
refresh. A native solution is zero-dependency and offline-clean, so HTMX was
dropped.

**What shipped.**
- **Regions.** `id="metrics"` and `id="grid"` mark the two refreshable regions.
- **`_refresh_script`** (replaces `_hub_events_script`): a `setInterval(…,10000)`
  timer plus an `EventSource` on `/v1/events` both call `refresh()`, which
  fetches `window.location.href` (with the `X-Halyard-Fragment` header),
  DOM-parses the response, and sets `cur.innerHTML = next.innerHTML` for each
  region. A `pending` flag debounces overlap. Fail-safe `try/catch`; on JS-off
  the page still renders fully on load.
- **Re-init after swap.** Swapping innerHTML discards the panels' event
  listeners and resets order/collapse, so after a swap `refresh()` calls
  `window.HalyardBootTables()` (sort) and a new idempotent
  `window.HalyardApplyLayout()` (restore saved order, re-add controls — guarded
  against double-wiring — and re-apply collapse). This is the load-bearing
  detail: today those survive only because the full reload re-runs the layout
  script; the hook preserves them across an in-place swap.
- **Drop** `<meta http-equiv="refresh" content="10">`.
- **Scroll/focus** are preserved for free (no navigation). The range/tab links
  are still real navigations, so `_scroll_preserve_script` stays for those.
- **No server change.** The client extracts regions from the full page (as the
  prior SSE script did); a server-side fragment endpoint was deemed an
  unnecessary optimization for a localhost page and skipped.

**Browser-verified** (preview tools): a `window` probe set before the timer
fired still held its value after (no full reload); the tagged first grid node
was gone (innerHTML genuinely swapped); layout controls were re-applied; and a
panel collapsed by hand stayed collapsed across the next refresh. No console
errors.

## Risks / mitigations

- Largest risk is #1 silently dropping an asserted substring across the table
  builders → mitigated by running the dashboard suite after each conversion.
- #3 changes asserted markup (`meta refresh`, the SSE swap idiom) → those
  specific tests were updated, and the live behaviour was browser-verified.
