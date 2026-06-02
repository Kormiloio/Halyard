# v5.13 — Tasks

- [x] Parse `?month=YYYY-MM` in the dashboard route handler that calls
      `_render_state` (`_send_dashboard`).
- [x] Add `wake_month_raw: str | None = None` kwarg to `_render_state`;
      resolve to a first-of-month `datetime` via `_resolve_wake_period`.
- [x] When the resolved period differs from `now`, build `wake_sessions`
      by filtering `state.all_sessions` to that year/month before
      computing `trail_heatmap` and the Wake-month label.
- [x] Replace the single `wake_month` template var with
      `wake_month` (plain label) + `wake_prev_href` + `wake_next_href`.
      Build hrefs with `_dash_href` (urlencode), preserving `range` and
      `tab`; drop `month` when the next click lands on current.
- [x] Update `dashboard.html.j2` Wake panel head to render the new nav.
- [x] Hide `›` when the active period is the current month.
- [x] Avoid double-escaping the hrefs (let Jinja autoescape do it once).
- [x] Tiny `.wake-nav` style in `dashboard.css` so the glyphs read as
      subdued nav, not a generic link.
- [x] Add `test_render_dashboard_wake_month_param_scopes_panel` covering
      default, `?month=2026-05`, and a bad-input fallback.
- [x] Verify with `uv run ruff check`, `uv run ruff format --check`,
      `uv run mypy src/halyard/dashboard.py`, the new test, and full
      suite (1504 passing on this branch vs 1503 on `main`; the 41
      pre-existing time-cliff failures are identical on both, unrelated
      to this change — flagged for a follow-up).
- [x] Browser-verify: navigate `/`, `/?month=2026-05`, click prev/next,
      confirm heading, pill ("active days"), heatmap cell count, and
      clean URL all update; no console errors.
- [x] Add v5.13 entry to `openspec/project.md`.
