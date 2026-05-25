# Design — v5.4 Dashboard templating + timezone ADR

## Dashboard templating

### Seam choice

The natural, lowest-risk seam is **page chrome vs. fragment composition**:

- The template owns static structure: the HTML document, the topbar (brand SVG,
  layout/theme/health controls), the `metrics` and `grid` section wrappers,
  every `<article>` panel wrapper with its `panel-head`/eyebrow/title, and the
  footer.
- Python keeps owning *what goes inside*: every `_voyage_panel`,
  `_moat_panel`, `_usage_panel`, `_*_table`, pill, metric, and script is built
  by the same function as before and passed in as a context variable.

This removes ~260 lines of inline HTML from `dashboard.py` without touching a
single panel builder, so the blast radius is the page skeleton only.

### Escaping model

`autoescape=True` (the project's stated intent for HTML templates; the invoice
template stays `autoescape=False` because it emits Markdown). Every injected
value is **already** escaped via `_e` (= `html.escape`) or is server-rendered
HTML, so each placeholder uses `|safe`. This makes the template output
byte-equivalent to the previous f-string: `_e(...)`-wrapped scalars stay
single-escaped; HTML fragments pass through verbatim. Literal template text is
never auto-escaped by Jinja, so the static HTML is emitted as-written.

### Environment lifecycle

`_dashboard_template()` builds a `FileSystemLoader` Environment over
`src/halyard/templates/` and is wrapped in `functools.lru_cache(maxsize=1)`,
so the Environment and parsed template are created once per process and reused
across the 10 s auto-refresh and every Hub-event fragment fetch. `Template` is
imported only under `TYPE_CHECKING` (string annotations via
`from __future__ import annotations`), so there is no import-time cost when the
dashboard is never rendered.

### Verification

- 100 existing dashboard render/security/layout/sort/stats/moat tests pass
  unchanged — they assert on the exact ids, classes, CSS/JS strings, and
  `data-panel`/`data-hub-fragment` attributes the template must preserve.
- New `tests/test_v54_dashboard_templating.py` locks the seam itself: template
  ships in the package dir, the Environment is cached, and the rendered page
  retains the template-owned chrome markers.
- ruff + ruff format + mypy clean on the changed file.

## Timezone ADR

No code change — the ADR records the *existing, verified* behaviour and the
rationale so reviews stop re-opening it:

- Collectors stamp naive-local time (bare `datetime.now()` / `strftime`).
- The wire format carries no offset; `_to_naive_local` is the single read-side
  coercion point for any tz-aware row.
- `_log_error` / `log_diagnostic` and PR/outcome resolution use UTC.

The ADR states the known limitation (cross-timezone aggregation is not sound
today) and the additive future path (optional `tz=` IANA token via the v2.75
extensible-token mechanism, converted to UTC only at an enterprise aggregation
boundary) — explicitly *not built*, gated on Halyard-Enterprise pull.

## Rejected alternatives

- **FastAPI/Starlette port** — unjustified for a localhost single-user
  server-rendered bridge; adds an async runtime and dependency surface for no
  user benefit.
- **UTC-internal-everywhere** (the reviewer's timezone suggestion) — wrong
  cost/benefit for a local-first plain-text tool; would force a breaking format
  migration. Partially adopted later via the optional `tz=` token.
- **Per-panel template extraction now** — larger surface, more substring-
  breakage risk; deferred to later increments on top of this seam.
