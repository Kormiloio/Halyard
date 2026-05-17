# v2.72 — Declarative field registry: Tasks

Status: **proposed (spec only, not started).** Optional refactor,
not hardening. Behaviour-pinned and explicitly cancellable at the
decision gate.

## Phase 0 (BLOCKING — pin before refactor)
- [ ] `tests/test_v272_round_trip.py`: property-based round-trip over
  adversarial values for every serialized field +
  `to_log_line(from_log_line(x)) == x`
- [ ] Golden corpus fixture captured from the *current* code; assert
  byte-identical output
- [ ] Gate: both pass on unrefactored `ai_log.py` first

## Build (only if Phase 0 green)
- [ ] Audit: list every optional key=value field and classify it as
  registry-1:1 vs explicit exception (branch-tag promotion, any
  legacy alias). Record the exception allow-list in this file
- [ ] `FieldSpec` + `FieldKind` + ordered `_FIELDS` tuple (order =
  current emit order, part of the byte-identical contract)
- [ ] `to_log_line()` tail iterates `_FIELDS`; positional head
  unchanged
- [ ] `_parse_line_result()` tail = `_BY_KEY` dict dispatch;
  positional + `s`/length guards + exceptions unchanged
- [ ] Registry-coverage test: every optional field is in `_FIELDS`
  or the explicit exception allow-list
- [ ] Full existing suite green with **zero** expected-output edits

## Docs
- [ ] `openspec/project.md` roadmap entry + status/test count
- [ ] Note in `ai_log.py` module docstring: registry is the single
  source for optional-field wire handling

## Decision gate
- [ ] Net: fewer lines AND single edit-site per new field AND zero
  behaviour diff. If not all three → **abandon, record, keep manual
  code** (acceptable outcome)

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
