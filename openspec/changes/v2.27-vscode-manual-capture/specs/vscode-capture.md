# Spec: VS Code Manual Capture

## Requirement: VS Code task installer

Halyard MUST provide a command named `install-vscode-tasks`.

### Scenario: task file is absent

WHEN `halyard install-vscode-tasks` is run in a workspace with no
`.vscode/tasks.json`
THEN Halyard creates `.vscode/tasks.json`
AND the file contains a task labeled "Halyard: Record VS Code AI session"
AND the task invokes `record-session` with `--tool vscode`.

### Scenario: task file already has unrelated tasks

WHEN `.vscode/tasks.json` already contains unrelated tasks
THEN Halyard preserves those tasks
AND appends the Halyard task without deleting user configuration.

### Scenario: installer is run twice

WHEN `halyard install-vscode-tasks` is run more than once
THEN the Halyard task is not duplicated
AND Halyard task inputs are not duplicated.

## Requirement: VS Code manual session records

### Scenario: user records a VS Code session

WHEN the user runs `halyard record-session --tool vscode --model github-copilot`
THEN Halyard appends a valid `ai-sessions.log` record
AND the record has `tool=vscode`
AND the record has `source=manual`.

## Requirement: VS Code surfaces

### Scenario: Passport

WHEN a session with `tool=vscode` exists
THEN the Passport includes a "VS Code" stamp.

### Scenario: Dashboard and TUI

WHEN dashboard or TUI renders a session with `tool=vscode`
THEN that session uses the VS Code marker instead of the generic unknown-tool
marker.

## Requirement: honest limitation

Halyard MUST document that VS Code/Copilot support is manual/editor-task capture
until a public VS Code or Copilot session hook/API exists.
