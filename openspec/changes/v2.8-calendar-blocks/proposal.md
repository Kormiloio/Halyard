# Proposal: v2.8 — Calendar Blocks

## Why this change

AI sessions are invisible in calendars. A developer who spends three hours on
a Gemini-assisted refactor, two hours debugging with Claude Code, and one hour
in a Cursor session has no way to show that time to a client, a manager, or
themselves — unless they manually block their calendar.

Halyard has the data. Every session has a start time, end time, tool, project,
model, and cost. The only missing step is exporting it as calendar events.

`halyard schedule` fills that gap: it reads sessions from the log and writes a
`.ics` file that any calendar app (Apple Calendar, Google Calendar, Outlook,
Fastmail) can import or subscribe to.

## What the command does

Reads AI sessions from the project directory or hub for the requested period
and emits a valid iCalendar (RFC 5545) file. Each session becomes one VEVENT:

- Summary: `{tool} — {project}` (or `{tool} — unattributed`)
- Start/end: the session's recorded wall-clock times
- Description: model, cost, token counts, any tags

The output can be written to a file or stdout. No network access. No calendar
API. The file is the deliverable.

## Command

```bash
halyard schedule
halyard schedule --period week
halyard schedule --period all
halyard schedule --project acme:auth
halyard schedule --output ai-work.ics
halyard schedule --stdout
```

Default period: month. Default output: `ai-schedule.ics` in the project
directory (or current directory if running from hub).

## What the command does NOT do

- It does not push events to any calendar service.
- It does not delete or update previously exported events.
- It does not read the calendar — it only writes.
- It does not include prompt text, conversation content, or source code.

## Success criteria

- `halyard schedule` produces a valid `.ics` file importable by Apple Calendar
  and Google Calendar.
- Each session maps to exactly one VEVENT with correct DTSTART and DTEND.
- UIDs are stable: the same session always produces the same UID so duplicate
  imports do not create duplicate events.
- The command works offline with no API key required.
- Covered by unit tests for ICS generation and CLI behavior.
