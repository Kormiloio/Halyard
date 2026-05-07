# Spec: v2.4 — Data Integrity

## Overview

Two guarantees: (1) no session is ever silently discarded — unattributed
sessions go to a fallback log with a visible warning; (2) every `ai-sessions.log`
line is validated through a canonical `AiSession` serializer — malformed lines
go to a quarantine log, never silently dropped.

---

## Unattributed session handling

### WHEN a collector hook fires and no project directory or hub is found
THEN the session is written to `~/.halyard/unattributed.log` in standard
`ai-sessions.log` format, and the following is printed to stderr:
`[halyard] session saved to ~/.halyard/unattributed.log — run 'halyard assign-unattributed' to review.`

### WHEN `halyard report` is run and `~/.halyard/unattributed.log` is non-empty
THEN the report footer includes: `N unattributed sessions in ~/.halyard/unattributed.log
— run 'halyard assign-unattributed' to assign or discard them.`

### WHEN the user runs `halyard assign-unattributed`
THEN each unattributed session is presented one at a time with: start time,
end time, tool, model, cost_usd, and any available tags.
The user is prompted: `[a]ssign to project / [h]ub / [d]iscard / [s]kip`.

### WHEN the user chooses [a]ssign
THEN the user is prompted for a project slug. The session is appended to that
project's `ai-sessions.log`. The line is removed from `unattributed.log`.

### WHEN the user chooses [h]ub
THEN the session is appended to the hub's `ai-sessions.log`. The line is
removed from `unattributed.log`.

### WHEN the user chooses [d]iscard
THEN the line is removed from `unattributed.log`. Nothing is written anywhere.
The user is asked to confirm: `Discard this session? (y/N)`

### WHEN the user chooses [s]kip
THEN the session remains in `unattributed.log` and the next session is shown.

### WHEN `halyard assign-unattributed` is run and `~/.halyard/unattributed.log` is empty or absent
THEN the command prints: `No unattributed sessions.` and exits 0.

---

## Canonical AiSession serialization

### WHEN `AiSession.to_log_line()` is called
THEN it returns a single line in the canonical format with all fields in a
defined order. `None` optional fields are omitted (not written as empty strings).
The line does not contain a trailing newline.

### WHEN `AiSession.from_log_line(line)` is called with a valid line
THEN it returns an `AiSession` with all fields correctly typed and populated.

### WHEN `AiSession.from_log_line(line)` is called with a line missing required fields
THEN it returns `None` and logs the error to `~/.halyard/quarantine.log`:
```
# Parse error: missing field 'model'
# Original line: s 2026-05-07T10:00:00 ...
```

### WHEN `AiSession.from_log_line(line)` is called with a field that has an invalid type
THEN it returns `None` and logs to quarantine with the field name and value.

### WHEN `AiSession.from_log_line(line)` is called with a negative token count
THEN it returns `None` and logs to quarantine.

### WHEN `from_log_line(s.to_log_line()) == s` (round-trip)
THEN this must be true for all valid `AiSession` instances. Enforced by a
property test in the test suite.

---

## `halyard check-log` command

### WHEN the user runs `halyard check-log`
THEN the command reads the current project's `ai-sessions.log` (or the hub log
if outside a project), validates every line using `from_log_line`, and prints:
`215 lines valid.`

### WHEN the log has invalid lines
THEN the command prints each invalid line:
```
Line 47: missing field 'model'
  s 2026-05-07T10:00:00 2026-05-07T11:00:00 claude-code ...
Line 103: negative value for 'input_tokens': -5
  s 2026-05-01T09:00:00 ...
2 invalid lines found.
```
And exits with code 1.

### WHEN the user passes `--log <path>`
THEN that file is checked instead of the auto-detected log.

### WHEN the log file does not exist
THEN the command prints: `No log file found at <path>.` and exits with code 1.

---

## Collector migration: use `AiSession.to_log_line()`

### WHEN `append_session()` is called with an `AiSession`
THEN it calls `session.to_log_line()` to serialize. No ad-hoc string formatting
exists anywhere in `ai_log.py` or any collector module.

### WHEN `read_sessions()` encounters a line it cannot parse
THEN it writes the line to `~/.halyard/quarantine.log` and continues. It does
not raise an exception. The line is not included in the returned session list.
The caller is not notified per-line (the quarantine log is the record).
