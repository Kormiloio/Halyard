# Design: v2.32 - VS Code Extension and Metadata Parity

## Approach

This change is spec-first. Implementation should happen in later tasks only
after the PRD, ARD, and OpenSpec requirements are accepted.

The design has three layers:

1. Shared metadata vocabulary in `AiSession`.
2. Collector adapters that map each tool's native signals into that vocabulary.
3. A VS Code extension that uses the Halyard CLI as the only log writer.

## Shared Metadata Vocabulary

Add optional fields only. Old log lines remain valid.

Interaction fields:

- `interaction_count`
- `user_message_count`
- `assistant_message_count`
- `prompt_count`
- `accepted_suggestion_count`
- `rejected_suggestion_count`
- `interaction_data_available`

Outcome fields:

- `files_touched_count`
- `test_run_count`
- `test_status`
- `build_status`
- `outcome_data_available`

Timing fields:

- `human_active_seconds`
- `idle_seconds`

Provenance fields:

- `telemetry_source`
- `telemetry_trust`

Existing rich fields remain part of the parity vocabulary:

- `tool_calls`
- `tool_errors`
- `wall_seconds`
- `agent_active_seconds`
- `code_added`
- `code_removed`
- `model_breakdown`
- `branch`
- `commit_count`

## Serialization

Continue using `key=value` extensions on `s` lines. Booleans use
`true`/`false`. Enums use lower-case safe tokens. Missing means unavailable
unless an explicit `*_data_available=false` field is present.

Free-form values must be avoided. If needed, short notes remain under the
existing `note` field and retain current sanitization rules.

## Collector Mapping

### Claude Code

Use hook payloads and transcript event structure only for counts and usage
metadata. Do not persist transcript content. Candidate fields:

- tokens and cache tokens;
- branch;
- commit count;
- code delta;
- interaction or assistant event count if safely derivable;
- tool calls/errors if exposed by event structure.

### Cursor

Use hook payload fields and workspace root metadata. Candidate fields:

- tokens when present;
- workspace-derived attribution;
- branch;
- commit count;
- code delta;
- interaction counts if present in hook payload;
- accepted/rejected suggestions only if public APIs expose counts.

### Gemini CLI

Normalize existing rich history enrichment into the shared vocabulary. Candidate
fields:

- `session_id`;
- tokens and cache tokens;
- `tool_calls`;
- `tool_errors`;
- `wall_seconds`;
- `model_breakdown`;
- `code_added`;
- `code_removed`;
- `resume_command`;
- interaction/message counts where present.

### Codex Desktop

Use JSONL event types and token snapshots. Candidate fields:

- session timing;
- model;
- tokens when present;
- cwd-derived attribution;
- branch;
- commit count;
- interaction count from event types;
- token data availability.

### VS Code

Use extension-observed metadata and public VS Code APIs. Candidate fields:

- elapsed time;
- workspace scope;
- branch;
- model label;
- prompt/interactions count if observed;
- accepted/rejected suggestion count if available;
- file count without filenames;
- code delta;
- test/build status when invoked through extension commands or user entry.

## VS Code Extension Architecture

The extension should be a thin TypeScript package. It should:

- discover the configured `halyard` executable;
- run read-only status checks;
- show status bar state;
- expose commands;
- keep transient session state in VS Code workspace state;
- invoke Halyard CLI to write sessions;
- never parse or write `ai-sessions.log` itself.

## CLI Contract

Prefer extending `record-session` with optional metadata flags for MVP. If the
flag surface becomes too large, add a metadata-only JSON payload option.

All CLI inputs must pass through Python validation before serialization.

## Data Quality

Collectors must never write guessed zeroes. They should omit unavailable fields
or write explicit availability flags. Reports must distinguish:

- zero observed interactions;
- interaction data unavailable;
- interaction data manually entered;
- interaction data inferred.

## Privacy Review

Before implementation, run a privacy review for each collector and extension
surface. Each metadata field must answer:

- What native source provides this?
- Could it contain user content?
- How is content stripped?
- What is stored?
- What trust label applies?

