# v5.6 — Dashboard: panel templates, external CSS, native partial refresh

> Note: HTMX (the originally-proposed approach for #3) was evaluated and
> **rejected** — vendoring it offline needs the file in-repo and a CDN breaks
> Halyard's offline-first non-negotiable. #3 shipped as a zero-dependency
> native partial refresh that reuses the existing SSE machinery. See design.md.

## Why

v5.4 extracted the dashboard *page shell* into a Jinja2 template but left three
weaknesses in `dashboard.py` (still ~3,200 lines):

1. **Panel bodies are still Python f-strings.** ~25 builder functions
   concatenate HTML (tables, panels) inline, so layout and logic stay fused.
2. **`_CSS` is a ~440-line Python string** at the bottom of the module — no
   editor CSS tooling, and it bloats the source file.
3. **The refresh model is crude.** A 10 s full-page `<meta http-equiv="refresh">`
   re-renders everything (losing scroll/focus) *and* a custom `EventSource`
   script does client-side fragment extraction on top. Two overlapping
   mechanisms, one of them a full reload.

The architecture itself (server-rendered HTML over a localhost
`ThreadingHTTPServer`, no build step) is the right fit for a local-first
`pipx`-install OSS tool, so this is a refinement, not a framework swap. A
FastAPI/React rewrite was rejected (adds an async runtime + Node build for a
single-user loopback page).

## What changes (three phases, each independently green)

1. **External CSS (#2).** Move `_CSS` verbatim to
   `src/halyard/templates/dashboard.css`, read once via a cached `_load_css()`
   and injected into the existing `{{ css|safe }}` slot. Output is unchanged
   (CSS stays inlined in `<style>`), so the CSS-substring tests still pass —
   the win is real CSS tooling and a smaller module.
2. **Panel templates (#1).** Move the per-panel HTML (tables + panel bodies)
   into `src/halyard/templates/panels/*.j2`; the Python builders shrink to
   context-dict assembly. Continuation of the v5.4 shell seam. Verified against
   the 100+ dashboard render tests at each step.
3. **Native partial refresh (#3).** Replace the full-page `<meta refresh>` with
   an in-place swap: a 10s timer and Hub SSE events fetch the page and swap
   only the `#metrics` and `#grid` regions' contents, then re-run the
   table-sort and a new idempotent `HalyardApplyLayout` hook so column sort,
   saved panel order, and collapse state survive the swap. No navigation, so
   scroll/focus are preserved. Zero new dependency (HTMX rejected — offline-
   first). No-JS baseline still renders the full page on load.

## Impact

- Affected: `src/halyard/dashboard.py` (slimmed to logic), new
  `templates/dashboard.css`, new `templates/panels/*.j2`, HTMX vendored as a
  small static asset (no Node/build step; served from the templates/static
  dir).
- Behaviour: server-rendered output stays equivalent for #1/#2; #3 changes the
  *refresh mechanism* only (smoother updates, no full-page flash) and keeps a
  working no-JS fallback.
- Packaging: new `.css`/`.j2`/`.js` ship via hatchling's existing
  `templates/*` glob (same as `invoice.md.j2` / `dashboard.html.j2`).
- Out of scope: any change to panel *content*, the data layer, the OTLP/ingest
  endpoints, or the ThreadingHTTPServer model.
