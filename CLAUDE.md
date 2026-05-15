# Halyard — Claude Code Instructions

## Spec discipline

Before touching any code, read:
- `openspec/project.md` — roadmap and active focus sequence
- `openspec/changes/<version>/proposal.md` — why the change exists
- `openspec/changes/<version>/design.md` — how it is built
- `openspec/changes/<version>/tasks.md` — what is done and what remains

After implementing, update:
- `tasks.md` — tick completed items immediately, not in batch
- `design.md` — if implementation deviated from the design
- `openspec/project.md` — roadmap entry status and test count
- `docs/PRD-*.md` / `docs/ARD-*.md` — if behavior, priority, or scope changed

If the work has no changeset yet, create `openspec/changes/<version>/` with
proposal.md, design.md, and tasks.md before writing code.

## Project structure

- Source: `src/halyard/`
- Tests: `tests/` — run with `uv run pytest`
- Lint: `uv run ruff check .` and `uv run ruff format --check .`
- Types: `uv run mypy src/`
- Specs: `openspec/`
- Docs: `docs/`

## Hard rules

- `strategy/` is proprietary — never stage or commit anything from it.
- Enterprise modules live in `Kormiloio/Halyard-Enterprise`, not here.
- All new code must pass ruff, mypy, and the full test suite before commit.
