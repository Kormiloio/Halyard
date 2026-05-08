# Spec: v2.8 — Calendar Blocks

## Command: `halyard schedule`

### WHEN the user runs `halyard schedule`
THEN the command reads sessions from the project directory or hub for the
current calendar month and writes a valid `.ics` file to `ai-schedule.ics`
in the project directory.
Exit code is 0. A confirmation line is printed to stdout with the path and
session count.

### WHEN the user runs `halyard schedule --period week`
THEN only sessions from the last 7 days are included.
The same applies to `today`, `month`, and `all`.

### WHEN the user runs `halyard schedule --stdout`
THEN the ICS content is written to stdout and no file is created.

### WHEN the user runs `halyard schedule --output ai-work.ics`
THEN the ICS content is written to that path.

### WHEN no Halyard project is found and no hub is configured
THEN the command exits with code 1 and prints "No Halyard project found."

### WHEN the period contains zero sessions
THEN the command writes a valid (empty) ICS file with no VEVENTs
AND prints "0 sessions exported."

---

## ICS content requirements

### WHEN a session is exported
THEN each session maps to exactly one VEVENT
AND the DTSTART equals the session's start timestamp
AND the DTEND equals the session's end timestamp
AND the SUMMARY is `{tool} — {project}` where project is the session's
project slug or `unattributed` if absent
AND the DESCRIPTION includes the model, cost in USD, and input/output token counts

### WHEN the same session is exported twice
THEN both exports produce a VEVENT with the same UID
(UIDs are deterministic, derived from session start + tool + model + cost)

### WHEN a DESCRIPTION line exceeds 75 octets
THEN the line is folded per RFC 5545 §3.1 (CRLF + SPACE continuation)

---

## Command: `halyard seed-demo`

### WHEN the user runs `halyard seed-demo`
AND the project log already contains sessions
THEN the command prints a warning and asks the user to pass `--yes` to confirm.

### WHEN the user runs `halyard seed-demo --yes`
THEN approximately 30 realistic sessions are appended to `ai-sessions.log`
AND sessions span at least 3 projects, 3 tools, and 2 models
AND at least some sessions include rich telemetry (tool_calls, code_added)
AND the sessions are backdated across the current calendar month

### WHEN `seed-demo` completes
THEN the command prints a summary: how many sessions were written and which projects.
