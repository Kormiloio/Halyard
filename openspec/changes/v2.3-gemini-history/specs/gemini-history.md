# Spec: Gemini History Enrichment

---

## History file parsing

**WHEN** `parse_session_file()` is called with a valid history JSON path  
**THEN** it returns a `GeminiSessionSummary` with per-model stats aggregated  
**AND** `dominant_model` is the model with the highest `output_tokens`  
**AND** `cost_usd` is the sum of `calculate_cost()` applied per model  
**AND** `total_tool_calls` and `total_tool_errors` are counted from all `toolCalls` entries

**WHEN** `parse_session_file()` encounters malformed JSON or a missing file  
**THEN** it returns `None` (never raises)

**WHEN** a session uses only one model  
**THEN** `model_stats` has exactly one entry and `dominant_model` equals that model's name

**WHEN** a session uses multiple models  
**THEN** each model gets its own `GeminiModelStats` entry  
**AND** cost is summed across all models, not computed from a single model's rates

**WHEN** a message has `tokens.thoughts > 0`  
**THEN** thinking tokens are added to input_tokens for cost calculation

---

## History file lookup

**WHEN** `find_session_file(session_id)` is called  
**AND** a file matching `session-*-{session_id[:8]}.json` exists under `~/.gemini/tmp/`  
**THEN** that file path is returned

**WHEN** no matching file is found  
**THEN** `None` is returned

**WHEN** multiple files match the same session_id prefix  
**THEN** the most recently modified file is returned

---

## Hook enrichment

**WHEN** `handle_agent_stop()` fires  
**AND** the history file for the current `session_id` is found  
**THEN** token counts and cost are taken from the history summary, not the accumulated state  
**AND** `model` is set to the dominant model (highest output tokens)  
**AND** `tags` includes `tools:N` if any tool calls occurred  
**AND** `tags` includes `tool_errors:N` if any tool calls failed

**WHEN** `handle_agent_stop()` fires  
**AND** the history file is not found or is malformed  
**THEN** the existing accumulated-state behaviour is used (no regression)

**WHEN** a session uses only cheap utility sub-agents with no main model calls  
**THEN** the accumulated-state fallback is used if the history file does not contain the expected structure

---

## `halyard import-gemini` — basic import

**WHEN** `halyard import-gemini` is run  
**AND** there are session files not yet imported  
**THEN** each new session is appended to the appropriate `ai-sessions.log`  
**AND** the command prints a summary line per imported session  
**AND** exits with code 0

**WHEN** `halyard import-gemini` is run  
**AND** all sessions are already imported  
**THEN** the command prints "No new Gemini sessions to import."  
**AND** exits with code 0

---

## Deduplication

**WHEN** a session with `job_id=gemini:{session_id}` already exists in the log  
**THEN** `halyard import-gemini` skips that session

**WHEN** `halyard import-gemini` is run twice  
**THEN** no duplicate records are written

---

## Project attribution during import

**WHEN** a session file's project slug has a `.project_root` file  
**AND** that path contains `halyard.toml`  
**THEN** the session is written to that project's `ai-sessions.log`

**WHEN** the project dir has no `halyard.toml`  
**OR** the `.project_root` file is absent  
**THEN** the session falls back to the hub log

**WHEN** no hub is configured  
**THEN** the session is skipped and a warning is printed

---

## `--dry-run` flag

**WHEN** `halyard import-gemini --dry-run` is run  
**THEN** no files are written  
**AND** the sessions that would be imported are shown  
**AND** exits with code 0

---

## `--all` flag

**WHEN** `halyard import-gemini --all` is run  
**THEN** all project slugs under `~/.gemini/tmp/` are scanned  
**AND** sessions from projects without a local `halyard.toml` fall back to hub

**WHEN** `halyard import-gemini` is run without `--all`  
**THEN** only the current project's sessions are imported (based on CWD)
