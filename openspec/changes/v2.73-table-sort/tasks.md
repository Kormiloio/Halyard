# v2.73 — Sortable dashboard tables: Tasks

Status: **proposed (spec only, not started).** Cosmetic UX, not
launch-blocking. Quality bar: a wrong sort is worse than no sort.

## Build
- [ ] `_sortable_table_attrs(key)` helper — one source for the
  `data-sortable`/`data-sort-key` attribute strings
- [ ] Tag the 8 sortable tables + per-column `data-sort`
  (num/text/time/sev/off); wrap sortable `<th>` labels in a
  keyboard-operable `<button>` + `aria-sort`
- [ ] Emit `data-sort-val` (raw numeric/epoch) on ambiguous cells
  (cost, tokens, time) so the sort key is the model value, not the
  formatted label; `data-sev` on Health cells
- [ ] `_table_sort_script()` inline IIFE: delegated click sort,
  num/time/sev/text comparators, blanks-last, asc→desc→clear cycle,
  stable sort, `sessionStorage` persist + restore across the 10 s
  meta-refresh
- [ ] No-JS baseline unchanged (additive attributes/button only)

## Tests (`tests/test_v273_table_sort.py`)
- [ ] markup: every sortable table has unique `data-sort-key`;
  non-sortable cols `data-sort=off`; Health has `data-sev`
- [ ] `data-sort-val` correctness vs underlying model values
- [ ] sortable-set matches the proposal (new-table guard)
- [ ] no-JS golden: row order + cell text unchanged vs pre-v2.73
- [ ] comparator reference (num/time/sev/text, blanks-last, cycle)

## Docs
- [ ] `docs/PRD-local-activity-dashboard.md`: note sortable tables
  (UX principle "dense tables")
- [ ] Roadmap entry + status/test count in `openspec/project.md`

## Decision gate
- [ ] Any column whose sort key can't be made unambiguous is dropped
  from the sortable set, not shipped wrong. Record which (if any)

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
