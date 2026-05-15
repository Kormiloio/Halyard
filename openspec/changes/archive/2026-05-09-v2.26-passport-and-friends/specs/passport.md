# Spec: Passport

## Stamp earning

WHEN a session with tool="claude-code" exists in ai-sessions.log
THEN the Claude Code stamp is earned

WHEN a session with tool="cursor" exists
THEN the Cursor stamp is earned

WHEN a session with tool="vscode" exists
THEN the VS Code stamp is earned

WHEN a session with an unrecognized tool key exists
THEN a generic stamp is earned with the raw tool name and 🔧 icon

WHEN no sessions exist
THEN no stamps are earned

WHEN the same tool appears in 100 sessions
THEN exactly one stamp is earned for that tool (stamps are not duplicated)

## Passport in halyard honors

WHEN `halyard honors` is run
THEN a "Passport" section appears listing all earned stamps with icon and tool name

WHEN no stamps are earned (no sessions captured)
THEN the passport section shows "No ports of call yet."

## Passport in Captain's Quarters (dashboard)

WHEN the dashboard is rendered
THEN the Captain's Quarters panel includes a passport row showing earned stamp icons

WHEN 4 or fewer stamps are earned
THEN all stamps are shown inline

WHEN more than 4 stamps are earned
THEN all stamps are shown (no truncation — passport is a flat list)
