# Tasks: v2.8 — Calendar Blocks

## Spec and design

- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/calendar-blocks.md

## `src/halyard/schedule.py`

- [x] `_session_uid(s)` — deterministic SHA-1 UID per session
- [x] `session_to_vevent(s)` — VEVENT block with DTSTART, DTEND, SUMMARY, DESCRIPTION
- [x] `build_calendar(sessions)` — full VCALENDAR string
- [x] RFC 5545 §3.1 line folding for long content lines
- [x] DESCRIPTION includes: model, cost, tokens, tool_calls, code_delta, tags

## `src/halyard/cli.py` — `halyard schedule` command

- [x] `schedule` command with `--period`, `--project`, `--output`, `--stdout`
- [x] Resolve project_dir via `find_project_dir() or find_hub()`
- [x] Parse sessions, apply period + project filters
- [x] Write to file or stdout; print confirmation with session count
- [x] Exit 1 with message when no project found

## `src/halyard/cli.py` — `halyard seed-demo` command

- [x] `seed-demo` command with `--yes` guard
- [x] ~30 sessions across 4 projects, 3 tools, 2+ models
- [x] Rich telemetry on sessions (tool_calls, code_added, etc.)
- [x] Work health signals embedded: high error rate, repeated sessions, unattributed high-cost
- [x] Deterministic (random seed 42) — reproducible for demos
- [x] Warns when log already has sessions; requires `--yes` to proceed

## Tests (`tests/test_schedule.py`)

- [x] `test_uid_is_stable`
- [x] `test_uid_differs_across_sessions`
- [x] `test_uid_ends_with_halyard_suffix`
- [x] `test_vevent_contains_required_fields`
- [x] `test_vevent_unattributed_project`
- [x] `test_vevent_description_includes_model_and_cost`
- [x] `test_vevent_includes_tool_calls_when_present`
- [x] `test_vevent_includes_code_delta_when_present`
- [x] `test_vevent_omits_optional_fields_when_absent`
- [x] `test_build_calendar_wraps_in_vcalendar`
- [x] `test_build_calendar_empty_sessions`
- [x] `test_build_calendar_uses_crlf`
- [x] `test_schedule_cli_writes_file`
- [x] `test_schedule_cli_stdout`
- [x] `test_schedule_cli_exits_1_no_project`
- [x] `test_seed_demo_writes_sessions`
- [x] `test_seed_demo_warns_without_yes`

## Quality

- [x] Run full test suite — all passing (393 tests)
- [x] Run ruff — no new errors
- [x] Run mypy — no new errors
