# v5.4 — Dashboard page shell → Jinja2 + timezone decision record

## Why

A due-diligence-style architecture review flagged `dashboard.py` (~3,355 lines)
as a maintenance risk: the page is assembled as one giant Python f-string, so
layout and logic are fused and the file is hard to evolve. The same review
flagged "timezone naivety" as an enterprise-aggregation risk without
acknowledging that the naive-local choice is deliberate and already has a
coercion boundary.

This changeset takes the two findings from that review that are real and
proportionate (the other three — concurrency read-locking, a fallback
diagnostic log, and a Hub latency test — are handled separately in their own
changeset). It is the first, smallest increment of breaking up the dashboard
monolith, plus the missing written-down decision on time handling.

Scope was deliberately split to avoid a rewrite: Jinja2 is already a
dependency (used for invoices), so the cost here is extraction, not new
machinery. A full ASGI/FastAPI port was rejected — it is unjustified for a
localhost, single-user, server-rendered bridge with no client-side app.

## What changes

1. **Extract the dashboard page shell into a Jinja2 template.** The document
   chrome (doctype/head/topbar/metrics row/grid wrapper/footer/script includes)
   and per-panel scaffolding (`<article>` wrappers, `panel-head`, eyebrows,
   titles, pill slots) move from the `_render_state` f-string into
   `src/halyard/templates/dashboard.html.j2`. `_render_state` now composes the
   dynamic fragments (panels, pills, metrics, scripts) in Python — exactly the
   same helper calls as before — and passes them to the template.
2. **Document the timezone model.** New `docs/adr/0001-timezone-model.md`
   (+ `docs/adr/README.md` index) records the accepted decision: domain
   timestamps (sessions, timeclock) are naive-local with a single coercion
   boundary (`_to_naive_local`); machine logs and PR/outcome attribution use
   UTC; the cross-team-aggregation limitation and the additive `tz=`-token
   migration path are written down for the future Halyard-Enterprise layer.

## Impact

- Affected code: `src/halyard/dashboard.py` (page shell only — every panel
  builder is unchanged), new `src/halyard/templates/dashboard.html.j2`.
- Affected docs: new `docs/adr/` directory.
- Output is behaviour-preserving: all fragments are pre-rendered/pre-escaped
  HTML injected with `|safe`; `autoescape=True` matches the project's stated
  intent for HTML templates. The 100 existing dashboard render tests pass
  unchanged.
- Packaging: the template ships automatically — hatchling's wheel target
  already includes `halyard/templates/*.j2` (verified against the 0.2.1 wheel).
- Out of scope: per-panel template extraction (future increments), any change
  to panel content, the ThreadingHTTPServer, and the three concurrency/
  observability review items (separate changeset).
