# v5.13 — Wake month navigation

## Why

The Bridge dashboard's **Wake** panel renders an activity heatmap for the
current calendar month and labels it `Wake · <Month YYYY>`. There is no way
to look at previous months from the dashboard. Today the only way to view
May's heatmap on June 2 is to call `trail_heatmap()` from the CLI with a
hand-rolled datetime — which the dashboard's typical user (us, plus future
solo-dev adopters) will not do.

Owner asked on 2026-06-02: "in the calendar, how do I change the month to
look back at what I did in May." Answer today: you can't. This changeset
fixes that.

## What

Add a `?month=YYYY-MM` query param to `/` (the dashboard route) that scopes
the **Wake** panel — and only the Wake panel — to the named month. Render
`‹` / `›` links in the panel head to step one month back / forward, hiding
`›` when viewing the current month so the user can't navigate into the
future. An invalid or out-of-range value falls back to "current month" with
no error.

Scope kept tight on purpose:

- Only the **Wake** panel reacts to `?month=`. Service Record, Sessions,
  Health, Voyage etc. continue to read whatever window they read today
  (Service Record is a separate, unrelated bug discussed in the same
  conversation but not bundled here).
- No new data formats, no new files, no CLI surface. Pure read layer.
- `?range=` (Usage Analytics) and `?tab=` (Usage tab selector) keep working
  unchanged; the new param composes with them in generated links.

## Out of scope

- Changing the Service Record / Captain's Quarters lookback window (its
  own changeset will fix the "rank resets on the 1st of each month" bug).
- Persisting the chosen month across reloads. The query string already
  serves that purpose; no need for a cookie or local state file.
- Day-level drill-down from inside the heatmap.
