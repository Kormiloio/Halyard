# Tasks: v2.35 — Subscription Cost Allocation

## Dashboard display
- [x] AI Cost metric card checks `report.total_cost` and `ledger.total_allocated_usd`
- [x] Shows `~$X.XX` with "allocated from plans" sub-label when captured cost is $0.00
  and `ai-plans.toml` defines plans
- [x] Falls back to "$0.00 · captured API cost" when no plans configured
- [x] Uses existing `build_ledger()` and `read_ai_plans()` — no new data formats

## Quality gates
- [x] 952 tests passing
- [x] ruff check clean
- [x] mypy clean (71 source files)

## Docs
- [x] `openspec/project.md` updated
- [x] `docs/current-direction.md` updated
