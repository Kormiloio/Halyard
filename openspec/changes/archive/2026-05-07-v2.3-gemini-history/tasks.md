# Tasks: v2.3 — Gemini History Enrichment

## Spec & design
- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/gemini-history.md

## `src/halyard/collectors/gemini_history.py` (new module)
- [x] Define `GeminiModelStats` dataclass
- [x] Define `GeminiSessionSummary` dataclass with derived fields
- [x] Implement `parse_session_file(path) -> GeminiSessionSummary | None`
  - Aggregate per-model token counts from all `type=gemini` messages
  - Count tool calls and errors from `toolCalls[].status`
  - Add thinking tokens to input for cost purposes
  - Compute `cost_usd` by summing `calculate_cost()` per model
  - Derive `dominant_model` = model with highest output_tokens
  - Return None on any exception
- [x] Implement `find_session_file(session_id) -> Path | None`
  - Search `~/.gemini/tmp/*/chats/session-*-{session_id[:8]}.json`
  - Return most recently modified if multiple matches
- [x] Implement `find_all_session_files() -> list[Path]`
- [x] Implement `project_dir_for_slug(slug) -> Path | None`
  - Read `~/.gemini/history/{slug}/.project_root`

## `src/halyard/collectors/gemini_cli.py` — hook enrichment
- [x] In `handle_agent_stop()`, call `find_session_file(session_id)` after reading state
- [x] If history file found: use `GeminiSessionSummary` for model, tokens, cost
- [x] Add `tools:N` tag if `total_tool_calls > 0`
- [x] Add `tool_errors:N` tag if `total_tool_errors > 0`
- [x] If history file not found: fall back to existing accumulated-state path (no regression)

## `src/halyard/cli.py` — `halyard import-gemini`
- [x] Add `import-gemini` command
  - `--dry-run` flag
  - `--all` flag (all project slugs vs current project only)
- [x] Dedup by `job_id=gemini:{session_id}` — skip already-imported sessions
- [x] Project attribution: `project_dir_for_slug()` → halyard.toml check → hub fallback
- [x] Print per-session summary line on import
- [x] Print "No new Gemini sessions to import." if nothing new
- [x] Exit code 0 always (informational)

## Tests (`tests/test_gemini_history.py`)
- [x] `test_parse_session_file_single_model` — correct stats for single-model session
- [x] `test_parse_session_file_multi_model` — cost summed across models, dominant model correct
- [x] `test_parse_session_file_thinking_tokens` — thinking tokens added to input cost
- [x] `test_parse_session_file_tool_calls` — tool count and error count correct
- [x] `test_parse_session_file_malformed` — returns None on bad JSON
- [x] `test_find_session_file_found` — locates file by session_id prefix
- [x] `test_find_session_file_not_found` — returns None
- [x] `test_find_session_file_multiple_matches` — returns most recently modified
- [x] `test_project_dir_for_slug_found` — reads .project_root correctly
- [x] `test_project_dir_for_slug_absent` — returns None

## Tests (additions to `test_gemini_collector.py`)
- [x] `test_handle_agent_stop_uses_history_file` — when history file present, uses summary
- [x] `test_handle_agent_stop_fallback_no_history` — falls back when history not found
- [x] `test_handle_agent_stop_tool_tags` — tools:N tag added

## Quality
- [x] Run full test suite — all passing
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
