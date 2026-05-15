# Tasks: v2.9 — Onboarding Doctor

## Spec and design

- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/onboarding-doctor.md

## `src/halyard/doctor.py`

- [x] Define `DoctorCheck` and `DoctorReport`.
- [x] Implement project and `ai-sessions.log` checks.
- [x] Implement hub checks.
- [x] Implement Claude Code hook detection.
- [x] Implement Cursor hook detection.
- [x] Implement Gemini CLI hook detection.
- [x] Implement unattributed and quarantine state checks.
- [x] Implement active timer check.
- [x] Implement first-capture recency check.
- [x] Implement JSON-serializable report output.

## `src/halyard/cli.py`

- [x] Add `halyard doctor`.
- [x] Add `--json`.
- [x] Add `--first-capture`.
- [x] Add `--tool claude|cursor|gemini|all`.
- [x] Exit 0 when no error checks are present.
- [x] Exit 1 when one or more error checks are present.

## Documentation

- [x] Add `docs/troubleshooting.md`.
- [x] Document first-capture workflow.
- [x] Document hook installation checks.
- [x] Document unattributed and quarantine recovery.
- [x] Link troubleshooting from README onboarding flow.

## Tests

- [x] Add `tests/test_doctor.py`.
- [x] Test healthy project.
- [x] Test no project and no hub.
- [x] Test valid hub fallback.
- [x] Test each hook installed/missing state.
- [x] Test unattributed/quarantine warnings.
- [x] Test first-capture success, unattributed, and missing states.
- [x] Test JSON output schema.
- [x] Test CLI exit codes.

## Quality

- [x] Run full test suite.
- [x] Run ruff.
- [x] Run mypy.
