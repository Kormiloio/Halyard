# v5.15 — Tasks

## Phase 0 — Scaffold

- [x] Create `prototypes/` directory and `prototypes/.gitignore` that
      excludes `out/`.
- [x] Add `prototypes/dashboard_prettifier.py` entry point:
      calls `halyard.dashboard.render_dashboard(project_dir)`, injects
      `<style>…proto-overrides.css…</style>` before `</head>`, writes
      to `prototypes/out/index.html`. `--serve` flag spins a
      `http.server.ThreadingHTTPServer` on `:8766` that re-renders on
      every GET (so editing the override CSS gives a hot-reload feel).
- [x] Add `prototypes/proto-overrides.css` skeleton with seven labelled
      `/* === Move N: ... === */` blocks (empty).

## Phase 1 — Sparkline + delta helpers

- [x] Add `_per_day(items, key, when, days=14, now=None)` in the prototype
      script. Returns one float per day, oldest → newest. Generalised to
      take a `when` extractor so it isn't `AiSession`-specific — keeps
      it usable when v5.16 lifts it for other series (cost-per-day from
      ledger entries, etc.).
- [x] Add `_sparkline_svg(series, width=60, height=20, stroke="currentColor")`
      that returns an inline SVG `<polyline>` string. Auto-scales the
      series to fit; empty / all-zero series returns a flat midline.
- [x] Add `_delta_chip(series)` that returns
      `{"label": "+12%", "kind": "positive"|"negative"|"new"|"flat"}`.

> Implementation note: helpers ship in `dashboard_prettifier.py` as
> reference for v5.16, but the prototype itself uses a parallel JS path
> (see "stubbed in the prototype" in design.md) because production HTML
> does not emit per-day series. The JS mirrors the Python helpers' shape
> so the v5.16 lift is one-to-one.

## Phase 2 — Apply the seven moves

Each move populates one `/* === Move N === */` block in
`proto-overrides.css`. Implement in order, browser-verify after each.

- [x] Move 1 — Hero KPI (`.metrics-hero .metric:first-child`).
- [x] Move 2 — Sparklines + delta chips on every `.metric`.
- [x] Move 3 — Single-accent discipline (demote green/amber/red from
      non-status fills; cyan everywhere else).
- [x] Move 4 — Typography uplift (h1 36px / -0.02em, h2 17px / -0.01em).
- [x] Move 5 — Heatmap legend strip under `.usage-heatmap`.
- [x] Move 6 — Glass-card refinement (`backdrop-filter`, softer border,
      lifted shadow).
- [x] Move 7 — Responsive (drop `min-width: 920px`, add 1024px and
      640px breakpoints).

## Phase 3 — Owner review

- [x] Run `uv run python prototypes/dashboard_prettifier.py --serve`
      against a real local project; verify all panels render.
- [x] Browser-verify side-by-side with `halyard dashboard` (different
      ports — production on 7432, prototype on 8766).
- [x] Create `prototypes/NOTES.md` and record Owner's verdict per move:
      accept / reject / tweak (+ tweak description).
      → **Bundle rejected.** Production look on `:7432` preferred.
      Zero moves accepted. No v5.16 fold-in.

## Phase 4 — Document

- [x] Add v5.15 roadmap entry to `openspec/project.md` marking the
      prototype phase complete with the bundle-reject outcome.
- [x] ~~Open the v5.16 fold-in changeset stub~~ — not needed; bundle
      was rejected, nothing to fold in.
- [x] Tick every task in this file.

## Phase 5 — Cleanup (Owner-instructed)

- [x] Delete `prototypes/` (entire directory) per Owner instruction.
      Roadmap entry 89 in `openspec/project.md` is the sole surviving
      record of the attempt, including the lessons captured for any
      future prettifier pass. `prototypes/NOTES.md` is gone; its
      contents were folded into the roadmap entry before deletion.
