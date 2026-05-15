# Spec: VS Code Extension

## Requirement: extension delegates writes to Halyard CLI

The VS Code extension MUST use the installed Halyard CLI for durable session
writes.

### Scenario: user records a VS Code AI session

WHEN the user runs `Halyard: Stop and Record AI Work`
THEN the extension invokes the local Halyard CLI
AND Halyard appends the normalized session to `ai-sessions.log`
AND the extension does not write `ai-sessions.log` directly.

## Requirement: status bar scope visibility

The extension SHOULD show the current Halyard scope in the VS Code status bar.

### Scenario: workspace is inside a Halyard project

WHEN VS Code opens a workspace under a Halyard project
THEN the status bar shows that project scope
AND the user can open a command to inspect the resolved log target.

### Scenario: workspace uses hub fallback

WHEN no local project is found but a hub is configured
THEN the status bar indicates hub capture
AND the user can see the hub path in a safe local-only view.

## Requirement: metadata-only capture

The extension MUST capture metadata only.

### Scenario: user has an active editor

WHEN the extension records a session
THEN it MUST NOT read or persist editor text
AND it MUST NOT record filenames or paths
AND it MAY record safe counts such as elapsed minutes, branch, and
files-touched count.

### Scenario: user enters a note

WHEN the user enters a note
THEN the note is treated as explicit manual metadata
AND Halyard sanitizes it before writing.

## Requirement: extension-observed interaction counts

The extension SHOULD capture interaction counts when public APIs expose them or
when the extension itself observes Halyard commands.

### Scenario: count is available

WHEN a public VS Code or Copilot API exposes an accepted suggestion count
THEN the extension MAY pass `accepted_suggestion_count` to Halyard
AND MUST NOT include suggestion text.

### Scenario: count is unavailable

WHEN suggestion or prompt counts are unavailable
THEN the extension omits those fields
AND Halyard marks interaction data as unavailable where appropriate.

## Requirement: recover unfinished work blocks

The extension SHOULD recover unfinished work blocks without silent writes.

### Scenario: VS Code closes before stop

WHEN the extension restarts and finds a pending work block
THEN it prompts the user to record, discard, or continue
AND it MUST NOT write a recovered session without user action.

## Requirement: dashboard entry point

The extension SHOULD provide a command to open the local Halyard dashboard.

### Scenario: user opens dashboard

WHEN the user runs `Halyard: Open Dashboard`
THEN the extension invokes or opens the local dashboard for the resolved scope
AND it does not require a cloud service.

