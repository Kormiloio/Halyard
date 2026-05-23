# v3.3 — Cross-collector rejection capture: Tasks

Status: **shipped.**

## Phase 0 — read-only spikes

- [x] **Codex Spike:** Identified the user-denial marker in rollout
  logs: `"The user doesn't want to proceed with this tool use"`.
- [x] **Claude Code Spike:** Identified the user-denial marker in
  transcripts: `"The user doesn't want to proceed with this tool use"`.

## Phase 1 — Implementation

### Codex Desktop
- [x] Update `_parse_session_file` in `codex_app.py` to count
  rejections from `aggregated_output`, `message`, and `output` fields.
- [x] Ensure `interaction_data_available` is True for all imported
  sessions.

### Claude Code
- [x] Update `_read_from_transcript` in `claude_code.py` to detect
  rejections inside `is_error` blocks.
- [x] Pass the rejection count to `AiSession` in `handle_stop_hook`.

### Dashboard / TUI
- [x] Add "(overlaps tool_errors)" sub-label to rejection counts
  when the tool is `claude-code` or `codex`.

## Phase 2 — Testing

- [x] Create `tests/test_v33_cross_collector_rejection.py`.
- [x] Mocked rollout with denial event → verify `rejected_suggestion_count`.
- [x] Mocked transcript with denied `tool_result` → verify both
  `tool_errors` and `rejected_suggestion_count` increment.
- [x] Regression: `pytest tests/test_codex_importer.py tests/test_v260_claude_code_enrichment.py`.

## Phase 3 — Docs

- [x] Roadmap entry in `openspec/project.md` updated to Complete.
- [x] PRD §reporting note: explain the overlap for Claude Code and Codex.
- [x] Collector coverage table updated in `docs/collector-coverage.md`.
