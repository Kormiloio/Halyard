# Collector Metadata Coverage

This table shows which metadata fields each Halyard collector populates and
how the value is obtained. **Unavailable is not zero** — an omitted field
means the collector cannot observe it, not that no activity occurred.

| Collector | Tokens | Interaction | Timing | Outcome | Quality |
|---|---|---|---|---|---|
| **claude-code** | observed (transcript) | observed (transcript) | calculated (hook) | inferred (git) | captured (hook) |
| **cursor** | observed (payload) | observed (payload) | calculated (hook) | inferred (git) | captured (hook) |
| **gemini-cli** | observed (history) | — | calculated (hook) | inferred (git) | captured (hook) |
| **codex-app** | observed (rollout) | observed (rollout) | calculated (rollout) | inferred (git) | observed (rollout) |
| **windsurf** | — | observed (hook) | calculated (hook) | inferred (git) | observed (hook) |
| **vscode** | — | — | observed (editor) | — | manual (timer) |

## Key

- **observed:** Collector reads ground-truth data from the tool's own records (transcripts, payloads, logs).
- **calculated:** Value derived by Halyard from hook firing times or raw counts.
- **inferred:** Value guessed from context (e.g. current git branch).
- **captured:** Value explicitly provided by the tool during the capture event.
- **manual:** Value entered by the user (e.g. via `halyard start`).

## Field Mapping

| Field | claude-code | cursor | gemini-cli | codex-app | windsurf | vscode |
|---|---|---|---|---|---|---|
| `tool` | captured | captured | captured | captured | captured | captured |
| `model` | observed (transcript) | captured (payload) | observed (history) | observed (rollout) | captured (hook) | captured (timer) |
| `input_tokens` | observed (transcript) | observed (payload) | observed (history) | observed (rollout) | — | — |
| `output_tokens` | observed (transcript) | observed (payload) | observed (history) | observed (rollout) | — | — |
| `cost_usd` | calculated (pricing) | calculated (pricing) | calculated (pricing) | calculated (pricing) | — | — |
| `cache_read` | observed (transcript) | observed (payload) | observed (history) | observed (rollout) | — | — |
| `cache_write` | observed (transcript) | observed (payload) | observed (history) | — | — | — |
| `project` | inferred (cwd/timer) | inferred (cwd/timer) | inferred (cwd/timer) | inferred (cwd/timer) | inferred (cwd/timer) | captured (timer) |
| `branch` | inferred (git) | inferred (git) | inferred (git) | inferred (git) | inferred (git) | — |
| `source` | `sdk` | `sdk` | `sdk` | `sdk` | `sdk` | `manual` |
| `interaction_count` | calculated (transcript) | calculated (payload) | — | calculated (rollout) | calculated (hook) | — |
| `user_message_count` | observed (transcript) | observed (payload) | — | observed (rollout) | observed (hook) | — |
| `assistant_message_count` | observed (transcript) | observed (payload) | — | observed (rollout) | observed (hook) | — |
| `prompt_count` | observed (transcript) | observed (payload) | — | observed (rollout) | observed (hook) | — |
| `accepted_suggestion_count` | — | observed (payload) | — | — | — | — |
| `rejected_suggestion_count` | inferred (v3.3) | observed (payload) | n/a | inferred (v3.3) | — | — |
| `tool_calls` | observed (transcript) | observed (payload) | observed (history) | observed (rollout) | — | — |
| `tool_errors` | observed (transcript) | observed (payload) | observed (history) | observed (rollout) | — | — |
| `code_added` | inferred (git) | inferred (git) | observed (history) | — | inferred (git) | observed (editor) |
| `code_removed` | inferred (git) | inferred (git) | observed (history) | — | inferred (git) | observed (editor) |
| `files_touched_count` | yes | yes | — | — | yes | yes |
| `test_run_count` | — | — | — | — | — | — |
| `test_status` | — | — | — | — | — | — |
| `build_status` | — | — | — | — | — | — |
| `agent_active_seconds` | — | — | — | — | — | — |
| `human_active_seconds` | auto-timer (timeclock) | auto-timer (timeclock) | auto-timer (timeclock) | auto-timer (timeclock) | auto-timer (timeclock) | observed (editor events) |
| `idle_seconds` | — | — | — | — | — | — |
| `interaction_data_available` | set by collector | set by collector | set by collector | set by collector | set by collector | false (no interaction data) |
| `outcome_data_available` | — | — | — | set by collector | — | — |

## Notes

**claude-code:** Interaction counts come from parsing the Claude Code transcript
JSONL. If the transcript is absent or unreadable, `interaction_data_available`
is set to `false` and interaction fields are omitted. Since v3.3, rejections
are detected from transcript error messages; these counts overlap with
`tool_errors`.

**cursor:** Token and interaction counts come from the Cursor hook payload.
`prompt_count` is derived from the hook payload's session metadata. Rejections
are reported directly by Cursor and do not overlap with tool errors.

*Coverage monitoring (v3.15):* Cursor stores chat/composer state in SQLite
(`state.vscdb`), not enumerable per-session files, so `halyard doctor` monitors
it with a **best-effort coarse signal** — the mtime of those stores, never their
contents (parsing the schema would be fragile) — with a wider grace than the
file-based tools. It can therefore tell "the app was active recently but nothing
was captured" only approximately; treat its warning as a prompt to check the
hook, not a precise per-session reconciliation.

**gemini-cli:** Rich telemetry depends on the local Gemini history file. Rejection
capture is N/A because the tool lacks an inline approval UX or history markers.

The history file is the *whole-session* record. Both capture paths read all of
it — the live hook re-parses it every turn (writing the running cumulative total)
and `import-gemini` parses it once — so a session can produce several redundant
rows. Since v3.14, `parse_sessions` collapses all rows sharing a Gemini session
id into one canonical row (most-complete wins) at read time, so every surface
counts each session exactly once.

*Known limitation (Defect C, v3.14):* Gemini's `/quit` summary may list a
secondary utility/router model (e.g. `gemini-3.1-flash-lite` for
`utility_router`/`utility_summarizer`) that it does **not** write to the session
history `.jsonl`. Halyard's history-derived collectors only see the models Gemini
persists, so that utility-model usage is **not captured** (it is not fabricated
either — "unavailable is not zero"). The only sources that carry it are the
terminal `/quit` summary (not a persisted artifact) and OpenTelemetry (durations,
not per-model token counts).

**codex-app:** Data is imported from Codex Desktop's exported conversation
files. Since v3.3, rejections are detected from rollout event statuses; these
counts overlap with `tool_errors`.

**windsurf:** Native collector for Codeium Windsurf IDE. Captures session
timing and interaction counts (turns) autonomously via `hooks.json`. Token
counts are currently unavailable in hook payloads. Sessions are finalized
after 30 minutes of inactivity. Like Cursor, coverage monitoring (v3.15) is a
best-effort coarse signal based on the mtime of `~/.codeium/windsurf/cascade`
(never parsed), with a wider grace.

**vscode:** Manual capture tool via the VS Code extension. The extension observes
active editing time via VS Code workspace events. It does not have access to
conversation transcripts, so all interaction counts are unavailable.
`human_active_seconds` reflects editor focus time, not AI interaction time.
Explicit `record-session` commands can populate these fields manually.
