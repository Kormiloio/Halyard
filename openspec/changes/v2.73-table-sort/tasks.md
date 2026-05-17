# v2.73 — Sortable dashboard tables: Tasks

Status: **COMPLETE 2026-05-16 (1266 tests passing).** Cosmetic UX,
not launch-blocking. Quality bar held: no column ships a wrong sort.

## Build
- [x] `_stbl(key, cols, cls)` — single source for the
  `data-sortable`/`data-sort-key`/`data-cols` table-open attrs
- [x] Tagged sortable tables: recent-sessions, sessions-adrift,
  leakage, billable-evidence, usage-models, models, tools,
  bucket-*, ledger, ledger-full, timeclock. Per-column kinds via
  `data-cols` (t/n/m/s/x)
- [x] `data-sort-val` on ambiguous cells: Recent Sessions tokens
  (in+out sum), Sessions Adrift Time (epoch), Timeclock Time
  (minutes); `data-sev` on Health via `_session_sev` (0 ok / 1 warn
  / 2 error — never the glyph)
- [x] `_table_sort_script()` inline IIFE: delegated header
  click/keydown, num (`$ , % k M`)/time(`HH:MM`)/sev/text
  comparators, blanks-last, stable, asc→desc→clear, `sessionStorage`
  persist + restore across the 10 s `<meta refresh>`; `aria-sort`
  set at runtime
- [x] No-JS baseline unchanged (additive attributes only; server
  still emits fixed-sorted rows)

## Tests (`tests/test_v273_table_sort.py`, 6 cases)
- [x] `_stbl` shape; `_session_sev` ranks
- [x] sortable tables present + unique keys; sorter script wired
- [x] Recent Sessions `data-sort-val`/`data-sev`/`data-cols`
- [x] no-JS baseline: rows + visible text unchanged
- [x] Budget panel NOT marked sortable

## Docs
- [x] `docs/PRD-local-activity-dashboard.md`: sortable-tables note
- [x] Roadmap entry + status/test count in `openspec/project.md`

## Decision-gate outcomes (recorded)
- **Budget dropped from the sortable set.** It is card-based
  (`budget-item` divs), not a `<table>`; a separate card-sorter is
  out of scope and not worth the churn. Spend totals remain readable
  unsorted. Recorded rather than shipped wrong.
- **Deviation from design:** `<th>` are made operable at *runtime*
  by the script (cursor/role/tabindex/aria-sort + key handler)
  rather than wrapped in a server-rendered `<button>`. Lower
  regression risk (no thead/class rewrites across ~11 inline-string
  tables); no-JS users simply get today's fixed sort. Accessibility
  parity is preserved when JS is on.
- Sessions-Adrift Time and Timeclock Time use explicit
  `data-sort-val` (epoch / minutes) instead of parsing the formatted
  label — the ambiguous-cell rule from the design.

## Gate
- [x] `pytest` green (1266 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
