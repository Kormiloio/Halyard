# Tasks: v2.4 — Data Integrity

## Spec & design
- [ ] Write proposal.md
- [ ] Write specs/data-integrity.md
- [ ] Write design.md (serialization format, quarantine log, unattributed flow)

## `src/halyard/ai_log.py` — canonical serialization

### `AiSession` serialization methods
- [ ] Add `to_log_line(self) -> str` — canonical serializer, all fields in defined order, None fields omitted
- [ ] Add `@classmethod from_log_line(cls, line: str) -> AiSession | None` — parses and validates
  - Validate required fields: start, end, tool, model, input_tokens, output_tokens, cost_usd
  - Validate types: token counts are non-negative int, cost_usd is non-negative float
  - Write to quarantine log on any error; return None
  - Never raise — all failures go to quarantine

### `read_sessions()` migration
- [ ] Replace ad-hoc line parsing with `AiSession.from_log_line()` call
- [ ] On None return: write to quarantine log, skip line, continue reading
- [ ] Remove all ad-hoc parsing logic from `read_sessions()`

### `append_session()` migration
- [ ] Replace ad-hoc f-string serialization with `session.to_log_line()`

### Quarantine log
- [ ] Implement `_write_quarantine(original_line: str, error: str) -> None`
  - Append to `~/.halyard/quarantine.log`
  - Format: comment header with error + original line
  - Create file and parent dir if needed

## Unattributed session log

### Collector changes (all three: claude_code, cursor, gemini_cli)
- [ ] In `handle_agent_stop()` (and Claude Code equivalent): when `project_dir is None`, call `_write_unattributed(session)` and print warning to stderr
- [ ] Implement `_write_unattributed(session: AiSession) -> None` in `ai_log.py`
  - Append to `~/.halyard/unattributed.log` using `session.to_log_line()`
  - Create file and parent dir if needed
- [ ] Remove existing silent-return paths in all three collectors

### `halyard assign-unattributed` command
- [ ] Add command to `cli.py`
- [ ] Read `~/.halyard/unattributed.log`; exit 0 with message if empty/absent
- [ ] Present each session with: start, end, tool, model, cost_usd, tags
- [ ] Prompt: `[a]ssign / [h]ub / [d]iscard / [s]kip`
  - `a`: prompt for project slug, validate slug exists in a known project, append to that log
  - `h`: find hub, append to hub log
  - `d`: confirm, then remove line from unattributed.log
  - `s`: move to next session
- [ ] After all sessions processed: print summary (`N assigned, M discarded, K skipped`)
- [ ] Rewrite `unattributed.log` atomically after each decision (no partial state)

## `halyard report` — unattributed footer
- [ ] In `report` command: check if `~/.halyard/unattributed.log` is non-empty
- [ ] If so, add footer line: `N unattributed session(s) — run 'halyard assign-unattributed'`

## `halyard check-log` command
- [ ] Add `check-log` command to `cli.py`
  - `--log <path>` option (default: current project log or hub)
- [ ] Read log file line by line; validate each via `from_log_line`
- [ ] Report invalid lines with line number, field error, and original text
- [ ] Exit 0 if all valid; exit 1 if any invalid
- [ ] Print summary line in all cases

## Tests (`tests/test_ai_log_serialization.py`)
- [ ] `test_to_log_line_round_trip` — `from_log_line(s.to_log_line()) == s` for full session
- [ ] `test_to_log_line_optional_fields_omitted` — None fields not in output
- [ ] `test_from_log_line_valid` — parses known-good line correctly
- [ ] `test_from_log_line_missing_required_field` — returns None, writes quarantine
- [ ] `test_from_log_line_negative_tokens` — returns None, writes quarantine
- [ ] `test_from_log_line_bad_cost` — returns None, writes quarantine
- [ ] `test_read_sessions_skips_quarantine_lines` — malformed line skipped, others returned

## Tests (`tests/test_unattributed.py`)
- [ ] `test_write_unattributed_creates_file` — creates file and parent dir
- [ ] `test_assign_unattributed_empty` — prints "No unattributed sessions." and exits 0
- [ ] `test_assign_unattributed_assign_to_project` — line moved to project log
- [ ] `test_assign_unattributed_assign_to_hub` — line moved to hub log
- [ ] `test_assign_unattributed_discard` — line removed after confirmation
- [ ] `test_collector_writes_unattributed_on_no_project` — no silent drop

## Quality
- [ ] Run full test suite — all passing
- [ ] Run mypy — no new errors
- [ ] Run ruff — no new errors
