# v5.15 — Design

## Why a prototype, not an in-place edit

The v5.7 cycle proved that Owner-review of a redesigned dashboard works
best when the new look renders against real data in a parallel page the
Owner can flip between in two browser tabs. The same approach here keeps
production untouched while the seven prettifier moves are sanity-checked
on actual session data (not Lorem-ipsum mocks). It also makes per-move
accept/reject cheap: each move is its own CSS layer; the Owner can ask
to drop one without unwinding the others.

## File map

```
prototypes/
  dashboard_prettifier.py       # entry point — wraps render_dashboard()
  proto-overrides.css           # the seven moves, each in its own block
  out/                          # generated; gitignored
    index.html
  NOTES.md                      # Owner's accept/reject/tweak log
```

**Implementation swap (vs the original sketch).** The production
`dashboard.html.j2` inlines its CSS via `<style>{{ css|safe }}</style>`,
so there is no second-stylesheet hook to override. Rather than mirror
the entire shell template (which would silently drift from production
as panels change), the prototype script simply calls
`render_dashboard(project_dir)` to get the production HTML string, then
appends `<style>…proto-overrides.css…</style>` immediately before
`</head>`. The cascade still resolves overrides last because the inject
runs after the inline production `<style>`. This keeps the prototype
permanently in lock-step with production: every panel, macro, control,
and behaviour appears as it really does, and the only delta is the seven
override blocks. No `proto.html.j2`, no `proto.css` re-export — both are
deleted from the file map.

## Sparkline + delta computation — stubbed in the prototype

Per-metric series live nowhere in the current `DashboardState`, and
moves 1, 2, and 5 require new DOM (sparkline SVG, delta chip, heatmap
legend strip) that the production HTML does not emit. A CSS-only
override layer cannot create those nodes.

**Prototype approach.** Inject a small client-side script after
`</body>` that walks `.metric` and `.usage-heatmap` nodes and appends
the new DOM. The script:

1. Reads each metric's displayed value (e.g. ``$12.34``) and produces a
   **deterministic 14-point stub series** seeded by a hash of the value
   and label. Same metric ⇒ same shape across reloads; different
   metrics ⇒ different shapes. This is enough to evaluate the LOOK; it
   is not real data.
2. Renders an SVG `<polyline>` (60×20 default; 120×32 for the hero
   slot) into each card.
3. Computes a fake delta from the stub series — `(last_3 - prev_3) /
   prev_3` — and renders the chip. Polarity is colour-discreet (cyan
   for positive, muted for the rest); we explicitly do not paint
   negatives red because Halyard reserves red strictly for status.
4. Appends the "Less ▢▢▢▢▢ More" strip after `.usage-heatmap`.

A small banner under the brand mark says **"v5.15 prototype —
sparklines and deltas are visual stubs. Real-data wiring is v5.16
scope."** so the Owner is never misled into reading the shapes as
production trends.

Pure helpers (`_per_day`, `_sparkline_svg`, `_delta_chip`) ship in
`prototypes/dashboard_prettifier.py` even though the prototype itself
uses the JS path — they are the reference implementations the v5.16
fold-in will lift directly into `src/halyard/reports.py` (or a sibling
module). Keeping them next to the prototype keeps the design
conversation in one place.

Caching / real-data wiring is **explicitly out of scope** for v5.15.
The v5.16 fold-in proposal will decide whether to add a
`series: list[float]` field to `MetricSpec` or to compute the series
inside the template's macro call.

## The seven moves — concrete CSS sketch

### Move 1: Hero KPI

```css
.metrics-hero .metric:first-child {
  grid-column: span 2;
  min-height: 156px;
}
.metrics-hero .metric:first-child strong { font-size: 48px; }
.metrics-hero .metric:first-child .sparkline { width: 120px; height: 32px; }
```

`metrics-hero` is added to `.metrics` only when the hero card has a
non-zero value (don't promote an empty metric into the hero slot).

### Move 2: Sparklines + delta chips

```css
.metric { gap: 8px; }
.metric .sparkline { width: 60px; height: 20px; align-self: end;
                     color: var(--cyan); opacity: .85; }
.metric .delta { display: inline-flex; align-items: center; gap: 4px;
                 font-size: 11px; font-weight: 700; color: var(--muted);
                 padding: 2px 6px; border-radius: 999px;
                 background: rgba(255,255,255,.05); }
.metric .delta-positive { color: var(--cyan); }
.metric .delta-negative { color: var(--muted); }
.metric .delta-new      { color: var(--muted); font-style: italic; }
```

### Move 3: Single-accent discipline

```css
/* Demote: anything that used green/amber/red for non-status purpose
   gets re-keyed to cyan or muted. Keep the status pills/dots untouched. */
.metric-money strong { color: var(--text); }    /* was --green */
.bar-cell .bar      { background: var(--cyan); } /* was tool-coded */
.tool-V             { background: rgba(180,120,255,.10); } /* still purple,
                     only one demoted accent — keeps the tool legend readable */
```

### Move 4: Typography uplift

```css
h1 { font-size: 36px; font-weight: 700; letter-spacing: -0.02em; }
h2 { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; }
.metric strong { font-weight: 700; letter-spacing: -0.01em; }
```

### Move 5: Heatmap legend

```css
.usage-heatmap-legend {
  display: flex; align-items: center; gap: 6px; margin-top: 10px;
  font-size: 11px; color: var(--muted);
}
.usage-heatmap-legend .swatch {
  width: 12px; height: 12px; border-radius: 3px;
}
```

### Move 6: Glass-card refinement

```css
.panel, .metric {
  border-color: rgba(255,255,255,.06);
  background: linear-gradient(180deg, rgba(255,255,255,.04),
                              rgba(255,255,255,.01)), rgba(16,27,32,.78);
  backdrop-filter: blur(8px) saturate(115%);
  -webkit-backdrop-filter: blur(8px) saturate(115%);
  box-shadow: 0 12px 36px rgba(0,0,0,.32);
}
```

### Move 7: Responsive

```css
body { min-width: 0; }                 /* drop the 920px floor */
.shell { width: min(1440px, calc(100vw - 32px)); }

@media (max-width: 1024px) {
  .grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .span-7, .span-12 { grid-column: span 6; }
  .span-5, .span-4, .span-6 { grid-column: span 3; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics-hero .metric:first-child { grid-column: span 2; }
}
@media (max-width: 640px) {
  .grid { grid-template-columns: 1fr; }
  .grid > * { grid-column: span 1 !important; }
  .metrics { grid-template-columns: 1fr; }
}
```

## Trade-offs considered

- **One override file vs seven** — kept as one (`proto-overrides.css`)
  with seven labelled blocks. Seven files would let the Owner toggle
  each move via `<link>` swaps, but adds boilerplate. The labelled-block
  approach is faster to author and only marginally harder to triage.
- **Compute series in Python vs in JS** — Python. The whole dashboard
  is server-rendered and offline-first; sneaking client JS in to draw
  sparklines would break that promise. Inline SVG `<polyline>` is the
  cheapest static encoding.
- **Glass blur on every panel vs hero only** — every panel. Selective
  blur reads as accidental; uniform blur reads as a design language.
  Cost is one `backdrop-filter` per panel — cheap on modern browsers.
- **Light mode** — explicitly skipped. Adding a light theme to the
  prototype doubles the surface and isn't what the Owner asked for.
