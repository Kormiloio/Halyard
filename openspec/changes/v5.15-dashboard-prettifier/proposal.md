# v5.15 — Dashboard prettifier pass

## Why

The Bridge is functionally complete and structurally calm after the v5.7
"B+" tabbed overview, but it still reads like an internal admin tool, not
a polished analytics product. The Owner asked whether we can borrow
techniques from the subframe.com "data analytics website design examples"
roundup and apply them here. After cross-walking the article's 15 patterns
against `src/halyard/templates/dashboard.css`, the diagnosis is that most
patterns are already present in some form — what's missing is **emphasis,
discipline, and motion in the metric strip**:

- KPI cards all weigh the same — there is no hero metric.
- The accent palette has drifted to five colours (cyan, green, amber, red,
  purple) with no single dominant — the "single accent guides attention"
  principle from the article is violated.
- KPI numbers are static — no sparkline, no delta, no sense of trend.
- Headlines are 28px / weight not tightened — they don't anchor the eye.
- The activity heatmap has no legend.
- The page has a hard `min-width: 920px` floor and breaks at narrow widths.

Per the same playbook that worked for v5.7, the Owner asked to
**prototype first, ship later** — build the redesigned look in a
throwaway prototype so the new direction can be compared against the
production dashboard side-by-side, then fold the winning bits in.

## What changes

This proposal covers only **the prototype phase**. The fold-in to the
production templates is a separate (in-scope, follow-on) proposal that
will be written once the prototype direction is owner-approved.

1. **`prototypes/dashboard_prettifier.py`.** A standalone script that
   renders the same `DashboardState` as production but through a parallel
   set of templates, so real session/health/usage data drives every
   panel. Run with `uv run python prototypes/dashboard_prettifier.py`
   (writes `prototypes/out/index.html`) or `--serve` to start a tiny
   `http.server` on `:8766` for live preview. No production code path
   is touched.
2. **Seven prettifier moves**, each implemented as an isolated CSS layer
   on top of the existing `dashboard.css` so the diff is reviewable:
   1. **Hero KPI treatment** — first metric in `.metrics` spans 2
      columns, number is 48px, with a 120×32 sparkline below.
   2. **Sparklines + delta chips on KPI cards** — every `.metric` gets a
      60×20 inline SVG sparkline of the last 14 days and a small
      `+12%` / `-3%` chip in the brand accent or muted (no green/red
      for delta polarity — we keep colour semantics for status only).
   3. **Single-accent discipline** — cyan is the brand. Green, amber,
      red are reserved for status (healthy / warning / error) and
      nothing else. Purple is demoted to a single tool-icon swatch
      (VS Code) and removed from chart fills.
   4. **Headline typography uplift** — `h1: 36px`, weight 700,
      `letter-spacing: -0.02em`. Eyebrows already strong.
   5. **Heatmap legend** — a "Less ▢▢▢▢▢ More" strip under
      `.usage-heatmap`, using the same five `.usage-l1..l4` swatches.
   6. **Glass-card refinement** — `.panel` and `.metric` gain
      `backdrop-filter: blur(8px) saturate(115%)`, softer
      `border-color: rgba(255,255,255,.06)`, lifted shadow.
   7. **Responsive breakpoints** — drop the `min-width: 920px` floor;
      add `@media (max-width: 1024px)` that collapses 12-col to 6-col,
      stacks metrics 2-up, hides nav controls into a "⋯" menu.

3. **`prototypes/NOTES.md`** — a one-pager capturing which of the seven
   moves the Owner accepts, rejects, or wants tweaked, written *during*
   the review session. This becomes the input to the fold-in proposal.

## Out of scope

- Touching `src/halyard/templates/dashboard.css` or
  `dashboard.html.j2` — those move only after Owner approval, in a
  v5.16 fold-in changeset.
- Wiring sparkline data into `DashboardState` for production. The
  prototype computes the per-day series inline from `all_sessions`;
  the production wiring (and the schema decision — cache the series on
  `MetricSpec`? compute on render?) belongs to the fold-in proposal.
- Tabs, panel on/off, per-column sort affordances — already shipped in
  v5.7 and v2.73; the prototype reuses them as-is.
- The Service Record rank-reset bug deferred from v5.13 — separate,
  unrelated behaviour fix.
- Light mode. Halyard's `color-scheme: dark` stays; the prototype only
  refines the dark surface.

## Success criteria

- `uv run python prototypes/dashboard_prettifier.py --serve` renders a
  redesigned page driven by real local data with all seven moves applied.
- Owner reviews side-by-side against `halyard dashboard` and records
  accept/reject/tweak per move in `prototypes/NOTES.md`.
- Zero changes to `src/halyard/` until the fold-in proposal lands.
