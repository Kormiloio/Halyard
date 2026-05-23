# v3.3 — Cross-collector rejection capture: Design

Status: **final.**

Following the approved proposal, v3.3 implements rejection capture for
Claude Code and Codex Desktop. Gemini CLI is excluded (N/A).

## Technical Approach

### 1. Codex Desktop
The `codex_app.py` collector was upgraded to parse rejection
events from the rollout JSONL.
- **Detector:** Search for the string `"user doesn't want to proceed"`
  in `aggregated_output`, `stdout`, `message`, and `output` fields
  across `exec_command_end`, `patch_apply_end`, `agent_message`,
  `custom_tool_call_output`, and `function_call_output` events.
- **Metric:** Map these events to `rejected_suggestion_count` on the
  `AiSession`.

### 2. Claude Code
The `claude_code.py` collector will be upgraded to distinguish user
denials from genuine tool errors in the transcript.
- **Detector:** Iterate over `tool_result` blocks in the transcript.
  A block with `is_error: true` is counted as a `tool_error`. If that
  same block contains a specific "permission denied" or "user
  rejected" marker in its `content` (to be confirmed by spike), it is
  ALSO counted as a rejection.
- **Metric:** Map these to `rejected_suggestion_count`.
- **Honest Labelling:** Ensure the TUI and dashboard render the
  rejection count with "(overlaps tool_errors)" when the tool is
  `claude-code`.

## Schema
No schema changes. `AiSession` already has:
- `rejected_suggestion_count: int | None = None`
- `interaction_data_available: bool = False`

## Component Changes

### `src/halyard/collectors/codex_app.py`
- Update `_parse_session_file` loop to detect and count rejections.
- Ensure `interaction_data_available` is set to `True`.

### `src/halyard/collectors/claude_code.py`
- Update `_read_from_transcript` to detect and count rejections from
  `tool_result` blocks.
- Update `handle_stop_hook` to pass the count to `AiSession`.

## Verification

### Spikes (Phase 0)
1. **Codex Spike:** Inspect raw rollout logs to find the rejection
   marker.
2. **Claude Code Spike:** Inspect raw transcripts to find the
   rejection marker in `tool_result`.

### Automated Tests
- Unit tests in `tests/test_v33_cross_collector_rejection.py`.
- Mocked transcripts/rollouts for both tools.
- Regression test: ensure `tool_errors` counts remain unchanged.
