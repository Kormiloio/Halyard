# Proposal: v2.27 — VS Code Manual Capture

## Problem

Halyard users do AI-assisted work in VS Code, usually through GitHub Copilot
Chat or inline completions. Unlike Claude Code, Cursor, and Gemini CLI, VS Code
and Copilot do not expose a stable public session-end hook with model, token, or
cost payloads that Halyard can consume.

Without a supported path, VS Code/Copilot work disappears from the ledger even
when the user wants the work represented in reports, Passport, and invoice
evidence.

## Decision

Add first-class manual/editor-task capture for VS Code:

- `halyard install-vscode-tasks` writes `.vscode/tasks.json`.
- The task runs `halyard record-session --tool vscode`.
- The task prompts for model/assistant label, minutes, and note.
- `vscode` earns a Passport stamp and has dashboard/TUI tool markers.
- Documentation must state clearly that this is manual capture, not native
  Copilot token capture.

## Non-Goals

- No VS Code extension in this change.
- No claim of automatic GitHub Copilot token usage or per-session cost capture.
- No prompt, chat transcript, file content, or code context capture.
- No mutation of VS Code settings outside `.vscode/tasks.json`.

## User Stories

- As a VS Code/Copilot user, I can run a local VS Code task after a Copilot work
  block and have Halyard record it as `tool=vscode`.
- As a Halyard user, I can see VS Code in Passport, dashboard/TUI tool mix, and
  reports without editing `ai-sessions.log` by hand.
- As a privacy-conscious user, I can track VS Code AI usage without capturing
  prompts, code, transcripts, or file contents.

## Acceptance Criteria

- Running `halyard install-vscode-tasks` creates or updates `.vscode/tasks.json`
  with a "Halyard: Record VS Code AI session" task.
- Re-running the installer is idempotent and preserves unrelated tasks/inputs.
- Running `halyard record-session --tool vscode ...` appends a valid session
  with `source=manual`.
- A `vscode` session earns a "VS Code" Passport stamp.
- Dashboard and TUI render a distinct marker for `vscode`.
- README and PRDs describe the manual-capture limitation honestly.
