# v2.73 — Sortable dashboard tables: Design

> Spec only. Verified against current `dashboard.py`: ~8 tables, all
> server-rendered; `<meta http-equiv="refresh" content="10">` at
> :720; existing inline-IIFE pattern (`_health_popup_script` :1200,
> scroll-preservation script). No per-table identity today.

## The hard part: surviving the 10 s reload

The page fully reloads every 10 s. Client sort must:

1. On a header click: sort `<tbody>` rows, set `aria-sort`, and write
   `{tableKey, colIndex, dir}` to `sessionStorage`
   (`halyard.sort.<tableKey>`).
2. On `DOMContentLoaded`: read any stored state and re-apply before
   first paint settles, so the 10 s refresh is visually stable.

`sessionStorage` (not `localStorage`): sort is a per-viewing-session
preference, cleared when the tab closes — matches the dashboard's
ephemeral-instrument model.

## Markup changes (server side, minimal)

Each sortable table gets a stable identity and per-column hints:

- `<table data-sortable data-sort-key="recent-sessions">`
- sortable `<th>` → `<th class="num" data-sort="num">` /
  `data-sort="text"` / `data-sort="sev"` (severity) /
  `data-sort="time"`; non-sortable `<th>` gets `data-sort="off"`.
- `data-sort-key` is a stable slug per logical table (not positional)
  so stored state survives unrelated layout changes.

A single helper (e.g. `_sortable_table_attrs(key)`) centralises the
attribute strings so every `<table>` site is a one-call change and
they cannot drift (same lesson as the v2.72 registry rationale —
one source, not N hand-synced sites).

## The sorter (one inline IIFE, ~50 lines, no deps)

`_table_sort_script()` returning a `<script>` block, appended near
the existing scripts:

- Delegate one `click` listener on `document` for
  `table[data-sortable] th[data-sort]:not([data-sort=off])`.
- Comparator by `data-sort`:
  - `num` — strip `$ , % spaces`, parse `k/M` → float; blanks/`—`
    sort last regardless of dir.
  - `time` — parse the cell's ISO/`HH:MM` (or a `data-sort-val`
    attribute the server can emit for unambiguous ordering).
  - `sev` — fixed rank map `{ok:0, warn:1, error:2, missing:3}` read
    from a `data-sev` attribute on the cell, never the glyph.
  - `text` — `localeCompare`, case-insensitive.
- Stable sort (decorate-sort-undecorate) so equal keys keep server
  order.
- Toggle: 1st click = asc, 2nd = desc, 3rd = clear → restore server
  order (keep the original row order in a JS array at load).
- Persist + restore via `sessionStorage` as above.

Where a rendered label is ambiguous to parse (tokens shown `8.5k`,
cost `$0.0000`, time `17:22`), the server emits an explicit
`data-sort-val` on that `<td>` with the raw numeric/epoch value; the
sorter prefers `data-sort-val` when present. This keeps the sort
correct without changing the visible text.

## Accessibility

- Sortable `<th>` wraps its label in a `<button>` (keyboard +
  screen-reader operable); `aria-sort` set to
  `ascending|descending|none` on the `<th>`.
- Non-sortable headers unchanged (no button, no pointer cursor).

## No-JS baseline

Server still emits today's fixed-sorted rows. JS only reorders an
already-correct table. Disabling JS = current behaviour exactly.
This is the regression floor and a test asserts the server output is
unchanged byte-wise except for the additive `data-*`/`button`
wrapper.

## Tests (`tests/test_v273_table_sort.py`)

1. Server markup: every table in the sortable set carries
   `data-sortable` + a unique `data-sort-key`; non-sortable columns
   carry `data-sort="off"`; Health/severity cells carry `data-sev`.
2. `data-sort-val` present and correct on ambiguous numeric/time
   cells (cost, tokens, time) — sort key matches the underlying
   model value, not the formatted string.
3. The set of sortable tables/columns matches the proposal table
   (guard against a new table silently shipping unsortable).
4. No-JS regression: rendered row order and cell text are unchanged
   vs the pre-v2.73 golden (additive attributes only).
5. (If a JS test harness is in use) sorter unit: num/time/sev/text
   comparators incl. blanks-last and the asc→desc→clear cycle.
   Otherwise the comparator logic is mirrored in a tiny pure-Python
   reference tested directly and the JS is kept a 1:1 transcription
   (documented).

## Decision / scope notes

- If emitting `data-sort-val` everywhere proves invasive, fall back
  to sorting only the unambiguous columns and drop the rest from the
  sortable set rather than ship a wrong sort. A wrong numeric sort is
  worse than no sort — this is the explicit quality bar.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. UI-enhancement changeset — full spec, no data/format change.
