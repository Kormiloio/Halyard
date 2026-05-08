# Tasks: v2.4 — Data Integrity

## Spec & design
- [x] Write proposal.md
- [x] Write specs/data-integrity.md
- [ ] Write design.md (serialization format, quarantine log, unattributed flow)

## Implementation note — 2026-05-07

A first data-integrity slice is implemented: malformed `ai-sessions.log` lines
are validated through `AiSession.from_log_line()` and quarantined, collectors
write otherwise-dropped sessions to `~/.halyard/unattributed.log`, `report`
surfaces the global unattributed log, and `check-log` validates logs.

The interactive `assign-unattributed` flow over `~/.halyard/unattributed.log`
is now implemented. The existing project-local assignment shortcut remains as a
fallback when the global unattributed log is empty.

## `src/halyard/ai_log.py` — canonical serialization

### `AiSession` serialization methods
- [x] Add `to_log_line(self) -> str` — canonical serializer, all fields in defined order, None fields omitted
- [x] Add `@classmethod from_log_line(cls, line: str) -> AiSession | None` — parses and validates
  - Validate required fields: start, end, tool, model, input_tokens, output_tokens, cost_usd
  - Validate types: token counts are non-negative int, cost_usd is non-negative float
  - Write to quarantine log on any error; return None
  - Never raise — all failures go to quarantine

### `read_sessions()` migration
- [x] Replace ad-hoc line parsing with `AiSession.from_log_line()` call
- [x] On None return: write to quarantine log, skip line, continue reading
- [x] Remove all ad-hoc parsing logic from `read_sessions()`

### `append_session()` migration
- [x] Replace ad-hoc f-string serialization with `session.to_log_line()`

### Quarantine log
- [x] Implement `_write_quarantine(original_line: str, error: str) -> None`
  - Append to `~/.halyard/quarantine.log`
  - Format: comment header with error + original line
  - Create file and parent dir if needed

## Unattributed session log

### Collector changes (all three: claude_code, cursor, gemini_cli)
- [x] In `handle_agent_stop()` (and Claude Code equivalent): when `project_dir is None`, call `_write_unattributed(session)` and print warning to stderr
- [x] Implement `_write_unattributed(session: AiSession) -> None` in `ai_log.py`
  - Append to `~/.halyard/unattributed.log` using `session.to_log_line()`
  - Create file and parent dir if needed
- [x] Remove existing silent-return paths in all three collectors

### `halyard assign-unattributed` command
- [x] Add command to `cli.py`
- [x] Read `~/.halyard/unattributed.log`; exit 0 with message if empty/absent
- [x] Present each session with: start, end, tool, model, cost_usd, tags
- [x] Prompt: `[a]ssign / [h]ub / [d]iscard / [s]kip`
  - `a`: prompt for project slug, validate slug exists in a known project, append to that log
  - `h`: find hub, append to hub log
  - `d`: confirm, then remove line from unattributed.log
  - `s`: move to next session
- [x] After all sessions processed: print summary (`N assigned, M discarded, K skipped`)
- [x] Rewrite `unattributed.log` atomically after each decision (no partial state)

## `halyard report` — unattributed footer
- [x] In `report` command: check if `~/.halyard/unattributed.log` is non-empty
- [x] If so, add footer line: `N unattributed session(s) — run 'halyard assign-unattributed'`

## `halyard check-log` command
- [x] Add `check-log` command to `cli.py`
  - `--log <path>` option (default: current project log or hub)
- [x] Read log file line by line; validate each via `from_log_line`
- [x] Report invalid lines with line number, field-level error text, and original text
- [x] Exit 0 if all valid; exit 1 if any invalid
- [x] Print summary line in all cases

## Tests (`tests/test_ai_log_serialization.py`)
- [x] `test_to_log_line_round_trip` — existing round-trip coverage in `tests/test_ai_log.py`
- [x] `test_to_log_line_optional_fields_omitted` — existing serializer coverage in `tests/test_ai_log.py`
- [x] `test_from_log_line_valid` — parses known-good line correctly
- [x] `test_from_log_line_missing_required_field` — returns None, writes quarantine
- [x] `test_from_log_line_negative_tokens` — returns None, writes quarantine
- [x] `test_from_log_line_bad_cost` — returns None, writes quarantine
- [x] `test_read_sessions_skips_quarantine_lines` — malformed line skipped, others returned

## Tests (`tests/test_unattributed.py`)
- [x] `test_write_unattributed_creates_file` — creates file and parent dir
- [x] `test_assign_unattributed_empty` — prints "No unattributed sessions." and exits 0
- [x] `test_assign_unattributed_assign_to_project` — line moved to project log
- [x] `test_assign_unattributed_assign_to_hub` — line moved to hub log
- [x] `test_assign_unattributed_discard` — line removed after confirmation
- [x] `test_assign_unattributed_skip` — line remains in unattributed log
- [x] `test_collector_writes_unattributed_on_no_project` — no silent drop

## Quality
- [x] Run full test suite — all passing (222 tests, 2026-05-07)
- [x] Run mypy — no new errors (2026-05-07)
- [x] Run ruff — no new errors (2026-05-07)
