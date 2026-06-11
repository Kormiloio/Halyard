# ARD: VS Code Extension and Metadata Parity

**Status:** Proposed
**Date:** May 14, 2026
**Related PRD:** `docs/PRD-vscode-extension-and-metadata-parity.md`
**OpenSpec change:** `openspec/changes/archive/2026-05-14-v2.32-vscode-extension-metadata-parity/`

---

## Architecture Decision

Build the VS Code integration as a thin local extension that delegates durable
data writes to the existing Halyard CLI. Extend `ai-sessions.log` with optional
metadata fields for interaction shape and outcome shape. Upgrade collectors to
populate those fields when public tool signals expose them.

The Python package remains the source of truth for:

- log schema and parser;
- append locking and amendments;
- project and hub discovery;
- attribution;
- pricing and trust labels;
- reports and dashboards.

The VS Code extension is a capture surface, not a second ledger
implementation.

## Constraints

- Local-first. No hosted service required.
- Plain text remains source of truth.
- No prompt, chat, source-code, file-content, filename, transcript, terminal
  output, or secret capture.
- Metadata fields are optional and backward-compatible.
- Missing data is represented as unavailable, not zero.
- Collectors may temporarily inspect local structured files only to aggregate
  counts and usage metadata.
- The same privacy boundary must apply to every tool.

## Components

### VS Code extension

Responsibilities:

- discover workspace root and git branch;
- show Halyard status in the status bar;
- expose Halyard commands in the command palette;
- start/stop a local work block timer;
- collect extension-observable counts;
- call the Halyard CLI with metadata arguments or a local JSON payload;
- open the local dashboard URL.

Non-responsibilities:

- parse or mutate `ai-sessions.log` directly;
- calculate pricing;
- store long-lived telemetry outside Halyard files;
- scrape Copilot private state;
- read or persist editor buffer content.

### Halyard CLI

Responsibilities:

- accept a richer manual/extension session payload;
- validate and sanitize metadata fields;
- append one normalized `AiSession`;
- mark source as `vscode-extension`;
- distinguish unavailable fields from zero values;
- preserve existing `record-session` behavior.

### Collector adapters

Each collector maps native tool signals into the shared metadata vocabulary:

- Claude Code hook and transcript event metadata;
- Cursor hook payload metadata;
- Gemini CLI hook and history metadata;
- Codex Desktop JSONL event metadata;
- VS Code extension-observed metadata.

Adapters must write only normalized metadata, not raw native payloads.

## Data Model

`AiSession` should keep baseline fields and gain optional metadata fields:

```text
interaction_count
user_message_count
assistant_message_count
prompt_count
accepted_suggestion_count
rejected_suggestion_count
files_touched_count
test_run_count
test_status
build_status
human_active_seconds
idle_seconds
interaction_data_available
outcome_data_available
telemetry_source
telemetry_trust
```

Existing rich fields remain:

```text
session_id
tool_calls
tool_errors
wall_seconds
agent_active_seconds
code_added
code_removed
model_breakdown
resume_command
branch
commit_count
```

All fields serialize through `key=value` extensions on `s` records. Complex
data must be summarized into counts or short enums. If a value cannot be safely
encoded without content, omit it.

## Trust Model

Metadata requires its own provenance:

- `captured`: directly provided by a public hook/API.
- `observed`: counted by Halyard or the extension from local event structure.
- `calculated`: derived from other metadata, such as elapsed time.
- `manual`: user-entered.
- `inferred`: guessed from overlap or git context.
- `unavailable`: tool does not expose the value.

Trust labels should be field-level where possible. If the log format remains
compact, collectors may write `telemetry_trust=<label>` for the overall
interaction metadata group.

## VS Code Extension Flow

1. Extension activates in a workspace.
2. Extension resolves the configured `halyard` executable.
3. Extension checks current Halyard scope by invoking a read-only CLI command
   or lightweight status command.
4. User runs `Halyard: Start AI Work`.
5. Extension records start timestamp, branch, and local counters in extension
   memory or VS Code workspace state.
6. User runs `Halyard: Stop and Record AI Work`.
7. Extension computes elapsed time and safe counts.
8. Extension calls Halyard CLI to append the normalized session.
9. Extension clears transient state and updates the status bar.

If VS Code closes before stop, the extension may offer to recover the pending
work block on next activation. Recovery must show the pending metadata before
writing.

## CLI Interface Options

MVP may extend `record-session`:

```bash
halyard record-session \
  --tool vscode \
  --source vscode-extension \
  --model github-copilot \
  --minutes 15 \
  --prompt-count 4 \
  --accepted-suggestion-count 7 \
  --files-touched-count 3 \
  --test-run-count 1 \
  --test-status passed
```

If this becomes too large, add:

```bash
halyard record-session --json /path/to/payload.json
```

The JSON payload must still be metadata-only and validated by Halyard before
serialization.

## Coverage Matrix

Each collector should publish a metadata coverage table with:

- field name;
- native source;
- trust level;
- unavailable behavior;
- privacy notes.

Reports should be able to explain why a field is missing for a tool.

## Security and Privacy

The extension must:

- never send data over the network;
- never read editor buffer text for telemetry;
- never persist prompt/chat/code text;
- never store filenames in Halyard metadata;
- never execute arbitrary shell text from the workspace;
- call only the configured `halyard` executable with structured arguments;
- escape or reject unsafe metadata values.

The CLI must:

- validate enum fields;
- cap free-form field length;
- reject newline, tab, and path-like unsafe values where not expected;
- write malformed payloads to an internal error path, not `ai-sessions.log`;
- keep old log parsing backward-compatible.

## Migration

No migration is required for existing logs. Old sessions simply have missing
metadata fields. The SQLite cache may need additive columns or a reset sentinel
depending on implementation. Plain text remains authoritative.

## Long-Lived Chat Sessions (v5.22)

A VS Code chat window routinely stays open for days, so the chatSessions
JSONL importer cannot treat "imported once" as "done" — that froze every
session at its first import snapshot (the codex pre-v5.2 / claude pre-v5.21
defect class, third instance). The mechanism, shared with those importers:

- **Growth-aware state.** `~/.halyard/copilot-imported` records
  `<session_id>\t<file_size>`; a session re-imports only when its chat file
  has grown. Legacy bare-id entries (including OTel capture marks, which are
  sizeless by nature) re-check once and are resolved by ledger coverage.
- **Read-time collapse.** Import rows carry `job_id=copilot:<session_id>`;
  `parse_sessions` collapses all rows sharing that job id to the
  most-complete one, so every surface counts a re-imported session exactly
  once. The key matches the job-id prefix only — OTel rows
  (`copilot-otel:<id>`, a disjoint namespace) and pre-v5.22 import rows
  carry `session_id` without it and never collapse.
- **Ledger coverage.** Before importing, the id is checked against every
  `github-copilot` row in the target ledger *not* written by this importer
  (OTel, pre-v5.22 imports, manual entries). Those rows cannot collapse with
  a fresh import row, so re-importing beside them would double-count; the
  session is skipped instead. The append-only log is never rewritten.

Spec: `openspec/changes/v5.22-copilot-growth-reimport/`.

## Open Questions

> **Partially resolved (v3.12):** VS Code 1.119+ exposes a public,
> standards-based source — OpenTelemetry (GenAI semconv) over a local OTLP
> endpoint — that carries model, token, and tool-call metadata for Copilot
> sessions natively (no internal-storage scraping). Halyard consumes it via a
> local receiver; see `openspec/changes/v3.12-vscode-otel-collector/` and
> `docs/copilot-otel.md`. It does **not** resolve the suggestion-count question
> below (the OTLP stream carries tool/token usage, not accept/reject counts).

- Which VS Code/Copilot APIs expose accepted and rejected suggestion counts
  without content?
- Should `files_touched_count` count git-tracked changed files only, or editor
  documents touched during the session?
- Should `test_status` be user-entered, command-observed, or both?
- Should the extension live in this repo or a separate `halyard-vscode` repo?
- Should the extension call `record-session` directly or a new
  `record-extension-session` command?

