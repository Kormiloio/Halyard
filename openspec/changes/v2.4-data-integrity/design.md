# v2.4 Design — Data Integrity

## Goals

- Canonical, round-trip-safe log serialization replaces ad-hoc f-strings.
- Malformed lines are quarantined, not silently dropped or crash-inducing.
- Sessions captured outside any project directory are preserved in a global
  unattributed log rather than discarded.
- A `check-log` command lets operators validate any log file.

---

## Serialization format

`AiSession.to_log_line()` is the single canonical serializer. All fields
are written in a fixed order; `None` optional fields are omitted.

```
s <start_iso> <end_iso> <tool> <model> <input_tokens> <output_tokens> <cost_usd> [key=value ...]
```

Optional KV fields (appended in order when non-None / non-empty):

| Key | Type | Notes |
|---|---|---|
| `project` | str | Project slug |
| `billing` | str | `api`, `seat`, `credits` (omitted when `api`) |
| `credits` | float | Seat/credits cost |
| `source` | str | e.g. git remote slug |
| `branch` | str | Active branch |
| `user` | str | Git email |
| `tags` | comma-list | Raw tag strings |
| `note` | str | Spaces replaced with `_`; newlines collapsed |
| `session_id` | str | UUID |
| `tool_calls` | int | |
| `tool_errors` | int | |
| `cache_read` | int | |
| `cache_write` | int | |
| `code_added` | int | |
| `code_removed` | int | |
| `resume_command` | str | |

`from_log_line(line)` parses, validates types and non-negative constraints,
and returns `AiSession | None`. It never raises — all parse failures write to
the quarantine log and return `None`.

---

## Quarantine log

**Path:** `~/.halyard/quarantine.log`

Written by `_write_quarantine(original_line, error)` whenever
`from_log_line()` rejects a line. Format:

```
# ERROR: <description>  <ISO timestamp>
<original line>
```

The file is append-only. Parent directory is created on first write.
`halyard doctor` surfaces a non-zero quarantine line count as a warning.

---

## Unattributed session log

**Path:** `~/.halyard/unattributed.log`

When a collector fires outside any Halyard project directory (no
`halyard.toml` found walking up from CWD), it writes the session to the
global unattributed log instead of discarding it silently.

All three collectors (claude_code, cursor, gemini_cli) use the same
`_write_unattributed(session)` helper in `ai_log.py`.

### `halyard assign-unattributed`

Interactive triage command. For each session in the unattributed log it
presents: start, end, tool, model, cost_usd, tags — then prompts:

```
[a]ssign  [h]ub  [d]iscard  [s]kip
```

| Action | Result |
|---|---|
| `a` | Prompt for project slug; append line to that project's log |
| `h` | Append line to hub log |
| `d` | Confirm; remove line from unattributed.log |
| `s` | Leave line in place; advance to next |

After all sessions: print `N assigned, M discarded, K skipped`.

The unattributed log is rewritten atomically after each decision (no
partial state on interrupt).

`halyard report` appends a footer line when the unattributed log is
non-empty: `N unattributed session(s) — run 'halyard assign-unattributed'`.

---

## `halyard check-log`

```bash
halyard check-log [--log <path>]
```

Reads a log file line-by-line, validates each data line via
`from_log_line()`, and reports:

- Line number, field-level error text, and the original line for each
  invalid entry.
- A summary line at the end.
- Exit 0 if all valid; exit 1 if any invalid.

Default path: current project log, then hub log.
