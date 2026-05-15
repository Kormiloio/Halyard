# Tasks: v2.27 — VS Code Manual Capture

## Implementation

- [x] Add `halyard install-vscode-tasks`.
- [x] Generate `.vscode/tasks.json` task for `record-session --tool vscode`.
- [x] Preserve existing VS Code tasks and inputs.
- [x] Make installer idempotent.
- [x] Add hidden compatibility alias `install-hook-vscode`.
- [x] Update `record-session` help text to mention `vscode`.

## Surfaces

- [x] Add `vscode` Passport stamp.
- [x] Add dashboard tool marker.
- [x] Add TUI tool marker.
- [x] Update README collector coverage and quickstart.
- [x] Update PRDs.
- [x] Add OpenSpec proposal/design/spec/tasks.

## Tests

- [x] Test task creation.
- [x] Test task merge/idempotence.
- [x] Test CLI command registration.
- [x] Test `record-session --tool vscode`.
- [x] Test VS Code Passport stamp.
- [x] Run full pytest suite.
- [x] Run ruff.
- [x] Run mypy.
