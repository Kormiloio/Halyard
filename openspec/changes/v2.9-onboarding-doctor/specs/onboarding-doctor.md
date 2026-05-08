# Spec: v2.9 — Onboarding Doctor

## Requirement: `halyard doctor`

Halyard MUST provide a local diagnostics command that reports setup and capture
health without requiring a cloud account.

### Scenario: healthy project

- WHEN the user runs `halyard doctor` inside a Halyard project
- AND `ai-sessions.log` exists and is writable
- THEN the command reports the project and log checks as healthy
- AND exits with code 0 if no error checks are present

### Scenario: no project and no hub

- WHEN the user runs `halyard doctor` outside any Halyard project
- AND no hub is configured
- THEN the command reports an error
- AND suggests `halyard init` or `halyard hub set`
- AND exits with code 1

### Scenario: no project but hub configured

- WHEN the user runs `halyard doctor` outside a project
- AND a valid hub is configured
- THEN the command reports ambient capture destination as the hub
- AND does not fail only because the current directory is not a project

## Requirement: hook diagnostics

Halyard MUST detect whether supported AI tool hooks are installed.

### Scenario: Claude Code hook installed

- WHEN `.claude/settings.json` or `~/.claude/settings.json` contains Halyard
  `cc-session` and `cc-hook` commands
- THEN `halyard doctor` reports Claude Code capture as installed

### Scenario: Claude Code hook missing

- WHEN no Halyard Claude Code hook is found
- THEN `halyard doctor` reports the check as warning or error according to the
  selected tool scope
- AND suggests `halyard install-hook`

### Scenario: Cursor hook missing

- WHEN `~/.cursor/hooks.json` is absent or missing Halyard cursor commands
- THEN `halyard doctor --tool cursor` reports an error
- AND suggests `halyard install-cursor-hook`

### Scenario: Gemini hook missing

- WHEN `~/.gemini/settings.json` is absent or missing Halyard Gemini commands
- THEN `halyard doctor --tool gemini` reports an error
- AND suggests `halyard install-gemini-hook`

## Requirement: collector state diagnostics

Halyard MUST surface recoverable collector state.

### Scenario: unattributed sessions exist

- WHEN `~/.halyard/unattributed.log` contains session records
- THEN `halyard doctor` reports a warning
- AND suggests `halyard assign-unattributed`

### Scenario: quarantine exists

- WHEN `~/.halyard/quarantine.log` exists
- THEN `halyard doctor` reports a warning
- AND suggests `halyard check-log` and reviewing the quarantine file

### Scenario: active timer exists

- WHEN `~/.halyard/active` contains a project slug
- THEN `halyard doctor` reports the active project
- AND explains that active timer attribution wins over git inference

## Requirement: first-capture verification

Halyard MUST provide a first-capture verification mode.

### Scenario: recent session captured

- WHEN the user runs `halyard doctor --first-capture`
- AND the project or hub `ai-sessions.log` contains a session ending in the
  last 30 minutes
- THEN the command reports first capture as healthy
- AND names the tool, model, project, and timestamp of the latest session

### Scenario: recent session landed unattributed

- WHEN no recent project or hub session exists
- AND `~/.halyard/unattributed.log` contains a recent session
- THEN the command reports first capture as warning
- AND suggests `halyard assign-unattributed`

### Scenario: no recent capture found

- WHEN no recent project, hub, unattributed, or quarantine evidence exists
- THEN the command reports first capture as error
- AND suggests checking hook installation and running the AI tool again

## Requirement: JSON output

Halyard MUST provide machine-readable doctor output.

### Scenario: JSON mode

- WHEN the user runs `halyard doctor --json`
- THEN stdout is valid JSON
- AND includes top-level `status` and `checks`
- AND each check includes `id`, `label`, `status`, `detail`, and `fix`
- AND no prompt, transcript, or source code content is included

