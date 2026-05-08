# Design: v2.8 — Calendar Blocks

## Module layout

```
src/halyard/
└── schedule.py      # ICS generation — pure functions over list[AiSession]
```

No new dependencies. Uses only the Python standard library (`hashlib`, `textwrap`).

## ICS format

RFC 5545 iCalendar. Each session → one `VEVENT`.

### UID generation

```python
import hashlib

def _session_uid(s: AiSession) -> str:
    raw = f"{s.start.isoformat()}{s.tool}{s.model}{s.cost_usd}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return f"{digest}@halyard"
```

Deterministic: re-exporting the same session always yields the same UID.
Calendar apps use UIDs to deduplicate — safe to import multiple times.

### VEVENT structure

```
BEGIN:VEVENT
UID:<sha1[:16]>@halyard
DTSTART:<YYYYMMDDTHHmmss>
DTEND:<YYYYMMDDTHHmmss>
SUMMARY:<tool> — <project or "unattributed">
DESCRIPTION:<multiline: model, cost, tokens, tags>
END:VEVENT
```

Timestamps are local time (no Z suffix, no TZID). The `.ics` file is a
portable snapshot, not a live subscription, so UTC conversion is not required.

### VCALENDAR wrapper

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Halyard//AI Session Schedule//EN
X-WR-CALNAME:AI Work Sessions
<VEVENTs>
END:VCALENDAR
```

## Line folding

RFC 5545 §3.1: lines longer than 75 octets must be folded with CRLF + SPACE.
The implementation folds long DESCRIPTION values.

```python
def _fold(line: str) -> str:
    """Fold a single iCal content line to max 75 octets per RFC 5545 §3.1."""
    if len(line.encode()) <= 75:
        return line
    result = []
    while len(line.encode()) > 75:
        chunk, line = line[:75], line[75:]
        result.append(chunk)
    result.append(line)
    return "\r\n ".join(result)
```

## CLI command

```
halyard schedule [--period today|week|month|all] [--project SLUG]
                 [--output PATH] [--stdout]
```

- Resolves `project_dir` via `find_project_dir() or find_hub()`
- Default output: `<project_dir>/ai-schedule.ics`
- `--stdout`: write ICS to stdout, no file written
- `--output PATH`: write to explicit path
- Prints confirmation + session count to stderr when writing a file
- Exit code 1 if no project found

## Public API

```python
def build_calendar(sessions: list[AiSession]) -> str:
    """Return a valid RFC 5545 iCalendar string for the given sessions."""

def session_to_vevent(s: AiSession) -> str:
    """Return a VEVENT block for a single session."""
```

## Testing

Pure functions over crafted session lists. No I/O required for the core
calendar builder. CLI tested with monkeypatched `parse_sessions`.

## Demo seed command

```
halyard seed-demo [--yes]
```

Writes ~30 realistic sessions across 4 projects and 3 tools into the current
project's `ai-sessions.log`. Designed to populate Glass Cockpit, the TUI, and
`halyard health` with meaningful data for demos.

Warns if the log already has sessions and requires `--yes` to proceed.
Sessions are backdated across the current calendar month.
