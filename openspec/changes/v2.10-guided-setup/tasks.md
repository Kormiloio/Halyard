# Tasks: v2.10 — Guided Setup

## Spec and design

- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/guided-setup.md

## `src/halyard/setup.py`

- [x] Define setup tool selection model.
- [x] Resolve selected tools from flags.
- [x] Build project/hub readiness summary.
- [x] Render next-step guidance.

## `src/halyard/cli.py`

- [x] Add `halyard setup`.
- [x] Add `--all`.
- [x] Add `--claude`.
- [x] Add `--cursor`.
- [x] Add `--gemini`.
- [x] Add `--yes`.
- [x] Add `--global-claude`.
- [x] Reuse existing hook installers.
- [x] Print `halyard doctor --first-capture` next step.

## Documentation

- [x] Update README Quickstart to prefer `halyard setup`.
- [x] Keep individual hook commands as manual/advanced options.
- [x] Update troubleshooting setup guidance.

## Tests

- [x] Add `tests/test_setup.py`.
- [x] Test `--all --yes` installs all tools.
- [x] Test selected tool flags.
- [x] Test `--yes` with no tool flags defaults to all tools.
- [x] Test no project/no hub guidance.
- [x] Test `--global-claude` forwards to Claude installer.

## Quality

- [x] Run full test suite.
- [x] Run ruff format check.
- [x] Run ruff check.
- [x] Run mypy.
