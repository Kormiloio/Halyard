# Tasks: v2.36 — Proof Score Transparency

## Voyage panel
- [x] Proof Score column shows `attr X% · tokens Y%` breakdown as sub-label
- [x] Attribution % computed from all-time sessions (`state.all_sessions`)
- [x] Token capture % computed from this-month sessions
- [x] Fix prompt "run halyard assign-unattributed" shown inline when `attr_pct < 100`
  and sessions exist
- [x] Combined proof score and css class unchanged (same formula)

## Quality gates
- [x] 952 tests passing
- [x] ruff check clean
- [x] mypy clean (71 source files)

## Docs
- [x] `openspec/project.md` updated
- [x] `docs/current-direction.md` updated
