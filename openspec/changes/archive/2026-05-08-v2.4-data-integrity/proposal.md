# Proposal: v2.4 — Data Integrity: No-Silent-Writes and Schema Validation

## Why this change

Halyard's non-negotiables include: *"No silent writes. Every AI-proposed change
is shown before it's applied."* The collection layer currently violates a
related principle in a quieter way: **no silent drops**.

Two failure modes exist today that discard data without telling the user:

### 1. Silent session drops in collectors

When `handle_agent_stop()` (Gemini CLI) or the equivalent Claude Code / Cursor
hook fires in a directory with no project attribution (no `halyard.toml` in any
parent, no hub configured), the collector calls `_reset_state()` and returns 0.
The session is gone. The exit code is 0. The user sees nothing.

This is not a rare edge case — it happens any time a user runs an AI tool
outside a Halyard project directory before they've configured a hub. It's the
exact situation new users hit on their first session.

### 2. Silent line drops on log read

`ai_log.py`'s `read_sessions()` silently skips lines it can't parse. A line
written by a future version of Halyard with an unrecognized field, a line
manually edited by a user, or a line truncated by a disk error is dropped with
no indication. The report totals are quietly wrong.

### The schema drift risk

`AiSession` is currently populated by ad-hoc string splitting in `read_sessions()`
and serialized by f-string formatting scattered across collectors. As the field
count grows (it went from 8 fields in v1 to 14 in v2.3), this approach produces:

- Subtle field ordering bugs (collectors that write `cache_read` but not
  `cache_write` produce lines that parse differently from collectors that write
  both)
- No canonical round-trip guarantee
- No way to assert "these two collectors write the same format"

### What three AI tools said

Claude CLI, Cursor, and Antigravity all flagged data integrity independently.
Cursor framed it as "data contracts." Antigravity framed it as structured
outputs. Claude CLI framed it as test coverage gaps. They're describing the same
underlying problem: the log format is implicit, and trust in the numbers depends
on an implicit format being honored everywhere.

## What this change does

### Unattributed session log

- When a collector cannot find a project directory or hub, it writes the session
  to `~/.halyard/unattributed.log` using the same `ai-sessions.log` format.
- It prints to stderr: `[halyard] session saved to ~/.halyard/unattributed.log
  — run 'halyard assign-unattributed' to review.`
- `halyard assign-unattributed` reads the unattributed log, presents each
  session with key metadata, and lets the user: (a) assign to a project
  (appends to that project's log), (b) assign to the hub, or (c) discard.
- `halyard report` includes an unattributed session count in the footer if
  `~/.halyard/unattributed.log` is non-empty.

### Canonical AiSession serialization

- `AiSession` gets `@classmethod from_log_line(cls, line: str) -> AiSession | None`
  with explicit field-level parsing and validation (types, required fields,
  non-negative token counts, sane cost range).
- `AiSession` gets `to_log_line(self) -> str` as the single canonical
  serializer. All collectors call this method — no ad-hoc f-string formatting.
- Lines that fail `from_log_line` validation are written to
  `~/.halyard/quarantine.log` with the original line and the parse error. They
  are never silently dropped.
- A round-trip property test verifies `from_log_line(s.to_log_line()) == s` for
  all valid session variants.

### `halyard check-log` command

- Reads an `ai-sessions.log` file (defaults to the current project's log) and
  validates every line using `from_log_line`.
- Valid lines: reports count. Invalid lines: reports line number, original text,
  and field-level error.
- Exit code 0 if all lines valid; exit code 1 if any invalid lines found.
- Useful as a pre-push git hook or CI step.

## What this change does NOT do

- No fuzzy dedup (near-duplicate session detection). The `job_id=` tag handles
  the primary dedup case. Fuzzy dedup needs a false-positive analysis and a
  separate spec.
- No retroactive re-parsing of existing logs. `halyard check-log` reports
  problems; it does not auto-correct them. Corrections are user-driven.
- No encryption or access control on the unattributed log. It is a plain-text
  file with the same trust model as `ai-sessions.log`.

## Key decisions

**Why `~/.halyard/unattributed.log` and not just stderr?**

Printing to stderr and discarding means the data is gone. Writing to a known
file means the data is recoverable — `halyard assign-unattributed` can always
be run later. The file also serves as evidence that the hook is firing even
before a project is configured, which is useful for debugging.

**Why quarantine, not skip, on parse failure?**

Silently skipping a malformed line produces wrong totals without any signal that
the totals are wrong. Quarantining preserves the original line for inspection
and makes the failure visible. The quarantine log is a plain text file —
users can read it, fix lines manually, and re-run `halyard check-log`.

**Why add `to_log_line()` / `from_log_line()` to `AiSession` rather than a
separate serializer module?**

`AiSession` is the canonical type for a session. Keeping serialization on the
type makes it easy to audit: there is one place to look, one place to test, one
place to update when a field is added. A separate serializer would require
keeping the two in sync without a structural guarantee.

## Success criteria

- Running any collector hook in a directory with no project attribution writes
  to `~/.halyard/unattributed.log` and prints a warning to stderr. No session
  is silently discarded.
- `halyard check-log` on a valid log exits 0: "N lines valid."
- `halyard check-log` on a log with a malformed line exits 1 and names the
  line number and field error.
- All three collector `handle_agent_stop()` functions use `AiSession.to_log_line()`.
  No ad-hoc formatting strings remain in collector code.
- Round-trip property test passes for all `AiSession` field combinations.
- `halyard report` shows unattributed session count when the file is non-empty.
