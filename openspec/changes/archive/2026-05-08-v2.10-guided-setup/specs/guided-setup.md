# Spec: v2.10 — Guided Setup

## Requirement: `halyard setup`

Halyard MUST provide a guided setup command that helps users install supported
AI tool hooks from one entry point.

### Scenario: non-interactive all setup

- WHEN the user runs `halyard setup --all --yes`
- THEN Halyard installs Claude Code, Cursor, and Gemini CLI hooks
- AND prints a readiness summary
- AND prints `halyard doctor --first-capture` as the next step

### Scenario: selected tool setup

- WHEN the user runs `halyard setup --claude --cursor --yes`
- THEN Halyard installs only Claude Code and Cursor hooks
- AND does not install Gemini CLI hooks

### Scenario: yes without tool flags

- WHEN the user runs `halyard setup --yes`
- THEN Halyard treats it like `halyard setup --all --yes`

### Scenario: no project and no hub

- WHEN the user runs `halyard setup` outside a Halyard project
- AND no hub is configured
- THEN Halyard prints a warning that capture has no destination
- AND suggests `halyard init` or `halyard init --hub`

## Requirement: safe hook installation

Guided setup MUST reuse the same hook-writing behavior as the individual hook
install commands.

### Scenario: hooks already installed

- WHEN setup installs a hook that is already present
- THEN the underlying installer remains idempotent
- AND no duplicate hook entry is written

### Scenario: hook settings file is not writable

- WHEN setup cannot write one tool's hook settings file
- THEN setup prints a clear error for that tool
- AND continues to the readiness summary instead of showing a Python traceback
- AND exits with code 1 after the summary

### Scenario: explicit Claude global install

- WHEN the user runs `halyard setup --claude --global-claude --yes`
- THEN Claude Code hooks are installed into the global Claude settings path
- AND local `.claude/settings.json` is not required

## Requirement: interactive prompts

Halyard SHOULD prompt users when no `--yes` flag is provided.

### Scenario: user declines a tool

- WHEN setup asks whether to install Cursor hooks
- AND the user declines
- THEN Cursor hooks are not installed
- AND setup continues with other selected or accepted tools
