# v2.73 — Sortable dashboard tables

> Spec only — proposed. Cosmetic UX; not launch-blocking. Post-launch
> unless explicitly pulled forward.

## Why

Every web-dashboard table is server-rendered with a single fixed sort
(sessions by time, projects by cost, etc.). A user scanning "which
session cost the most?" or "which project is heaviest?" can't reorder
— they read a fixed view. Clickable column sort is a standard,
expected affordance for dense operational tables (the dashboard's own
design target).

## What changes

Progressive-enhancement client-side column sort:

- Sortable `<th>` cells become clickable (toggle asc/desc); a small
  vanilla-JS sorter reorders the table's `<tbody>` rows in place. No
  backend, no new endpoint, no data/format change.
- **Sort state survives the 10 s meta-refresh.** The dashboard does a
  full `<meta http-equiv="refresh" content="10">` reload; a naive JS
  sort resets every 10 s and is useless. Sort state (per-table key +
  column + direction) is persisted in `sessionStorage` and re-applied
  on load. This is the load-bearing requirement, not the click
  handler.
- No-JS / pre-enhancement render is unchanged — the existing fixed
  server sort is the baseline, so nothing regresses.

## Sortable columns (per the review)

| Table | Default | Sortable columns |
|---|---|---|
| Recent AI Sessions | Time desc | Time, Cost, In/Out (total tokens), Health (by severity) |
| Sessions Adrift | Time desc | Time, Cost, Tool |
| Projects / Attribution | Cost desc | Project, Sessions, Cost |
| Models | Cost desc | Model, Sessions, Tokens, Cost, Share |
| Tools | Cost desc | Tool, Sessions, Tokens, Cost, Share |
| Budget / spend limits | Spend desc | Project, Spend, Limit, % used |
| Timeclock | Project | Project, Time |
| Leakage (adrift remotes) | Cost desc | Remote, Sessions, Cost |

Deliberately **not** sortable: free-text Note, the "Fix (proposed)"
column. The Health column sorts by **severity rank**
(ok < warn < error), never the glyph/text — an alpha sort there is
worse than none.

## Constraints honored

- Local-first, no network: pure inline JS, same pattern as the
  existing health-popup / scroll-preservation IIFEs.
- Numeric columns sort numerically: parse `$`, `,`, `%`, `k/M`
  suffixes; reuse the existing `<th class="num">` marker as the
  numeric signal.
- Accessible: `aria-sort`, real `<button>`/role semantics, keyboard
  operable.
- Trust labels and "missing" cells keep their meaning under sort
  (sort key derived from the underlying value, not the rendered
  label).

## Non-goals

- Server-side / cross-page sort, pagination, multi-column sort.
- Sorting the TUI tables (separate surface; out of scope).
- Any change to what the tables contain or how data is computed.
