# Tasks: v2.5 — CLI Decoupling

## Spec & design
- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/decoupling.md

## `src/halyard/hub.py` — Hub Service
- [x] Implement `get_hub_status() -> HubStatus`
- [x] Move `hub` command logic from `cli.py` to `hub.py`.

## `src/halyard/reports.py` — Report Service
- [x] Move pricing staleness check logic.
- [x] Implement `build_filtered_report` (merging period resolution and filtering).

## `src/halyard/orchestration.py` — New Module
- [x] Create module and move initialization templates.
- [x] Implement `scaffold_project`.
- [x] Implement `interactive_assign_unattributed`.

## `src/halyard/cli.py` — Cleanup
- [x] Update `init` command.
- [x] Update `hub` command.
- [x] Update `report` command.
- [x] Update `assign_unattributed` command.
- [x] Remove unused template strings and private helpers.

## Quality
- [x] Run full test suite — all passing
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
