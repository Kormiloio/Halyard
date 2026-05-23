# v2.72 — Declarative field registry: Tasks

Status: **shipped.**

## Phase 0 (BLOCKING — pin before refactor)
- [x] `tests/test_v272_round_trip.py`: property-based round-trip over
  adversarial values for every serialized field +
  `to_log_line(from_log_line(x)) == x`
- [x] Golden corpus fixture captured from the *current* code; assert
  byte-identical output
- [x] Gate: both pass on unrefactored `ai_log.py` first

## Build (only if Phase 0 green)
- [x] Audit: list every optional key=value field and classify it as
  registry-1:1 vs explicit exception (branch-tag promotion, any
  legacy alias). Record the exception allow-list in this file
- [x] `FieldSpec` + `FieldKind` + ordered `_FIELDS` tuple (order =
  current emit order, part of the byte-identical contract)
- [x] `to_log_line()` tail iterates `_FIELDS`; positional head
  unchanged
- [x] `_parse_line_result()` tail = `_BY_KEY` dict dispatch;
  positional + `s`/length guards + exceptions unchanged
- [x] Registry-coverage test: every optional field is in `_FIELDS`
  or the explicit exception allow-list
- [x] Full existing suite green with **zero** expected-output edits

## Docs
- [x] `openspec/project.md` roadmap entry + status/test count
- [x] Note in `ai_log.py` module docstring: registry is the single
  source for optional-field wire handling

## Decision gate
- [x] Net: fewer lines AND single edit-site per new field AND zero
  behaviour diff. If not all three → **abandon, record, keep manual
  code** (acceptable outcome)

## Gate
- [x] `pytest` green
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
