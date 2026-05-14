# Collector Metadata Coverage

This table shows which metadata fields each Halyard collector populates and
how the value is obtained. **Unavailable is not zero** — an omitted field
means the collector cannot observe it, not that nothing happened.

Trust labels:

| Label | Meaning |
|---|---|
| observed | Directly reported by the tool or its output |
| calculated | Derived by Halyard from git or filesystem state |
| inferred | Approximated from indirect signals |
| — | Not available from this collector |

## Field coverage by collector

| Field | claude-code | cursor | gemini-cli | codex-app | vscode-extension |
|---|---|---|---|---|---|
| `branch` | calculated (git) | calculated (git) | calculated (git) | calculated (git) | calculated (git) |
| `commit_count` | calculated (git) | calculated (git) | calculated (git) | calculated (git) | calculated (git) |
| `code_added` | calculated (git diff) | calculated (git diff) | observed (history) | — | calculated (git diff) |
| `code_removed` | calculated (git diff) | calculated (git diff) | observed (history) | — | calculated (git diff) |
| `wall_seconds` | calculated (stop − start) | calculated (stop − start) | observed (elapsed) | — | calculated (stop − start) |
| `interaction_count` | observed (transcript) | observed (payload) | observed (history) | observed (transcript) | — |
| `user_message_count` | — | observed (payload) | observed (history) | observed (transcript) | — |
| `assistant_message_count` | observed (transcript) | observed (payload) | observed (history) | observed (transcript) | — |
| `prompt_count` | — | inferred (payload) | observed (history) | — | — |
| `tool_calls` | — | observed (payload) | observed (history) | observed (transcript) | — |
| `tool_errors` | — | observed (payload) | observed (history) | observed (transcript) | — |
| `files_touched_count` | — | observed (payload) | — | — | — |
| `accepted_suggestion_count` | — | — | — | — | — |
| `rejected_suggestion_count` | — | — | — | — | — |
| `test_run_count` | — | — | — | — | — |
| `test_status` | — | — | — | — | — |
| `build_status` | — | — | — | — | — |
| `agent_active_seconds` | — | — | — | — | — |
| `human_active_seconds` | auto-timer (timeclock) | auto-timer (timeclock) | auto-timer (timeclock) | auto-timer (timeclock) | observed (editor events) |
| `idle_seconds` | — | — | — | — | — |
| `interaction_data_available` | set by collector | set by collector | set by collector | set by collector | false (no interaction data) |
| `outcome_data_available` | — | — | — | set by collector | — |

## Notes

**claude-code:** Interaction counts come from parsing the Claude Code transcript
JSONL. If the transcript is absent or unreadable, `interaction_data_available`
is set to `false` and interaction fields are omitted.

**cursor:** Token and interaction counts come from the Cursor hook payload.
`prompt_count` is derived from the hook payload's session metadata.

**gemini-cli:** Rich telemetry depends on the local Gemini history file at
`~/.gemini/history.jsonl`. If the file is absent when the hook fires, Halyard
falls back to the lighter hook payload and omits history-derived fields.

**codex-app:** Data is imported from Codex Desktop's exported conversation
files. `interaction_data_available` is set based on whether export data was
found. `code_added`/`code_removed` are not available because Codex Desktop
does not expose a git context at export time.

**vscode-extension:** The extension observes active editing time via VS Code
workspace events. It does not have access to conversation transcripts, so all
interaction counts are unavailable. `human_active_seconds` reflects editor
focus time, not AI interaction time.

**Manual / `record-session`:** All fields except `branch`, `commit_count`,
`interaction_data_available`, and `outcome_data_available` must be supplied
explicitly via flags. The command validates `--test-status`, `--build-status`,
and `--telemetry-trust` at input time.
