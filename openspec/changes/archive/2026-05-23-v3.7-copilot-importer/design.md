# v3.7 — GitHub Copilot Importer: Design

## Where

- **New module:** `src/halyard/collectors/copilot.py` — handles the discovery
  of `workspaceStorage` folders and the parsing of internal JSONL logs.
- **CLI Command:** `halyard import-copilot`: Scans and imports new sessions.
- **State File:** `~/.halyard/copilot-imported` — stores session UUIDs to
  ensure idempotency across imports.

## Discovery Logic

Copilot metadata is spread across multiple internal VS Code directories.

### 1. Workspace Discovery
Halyard walks `~/Library/Application Support/Code/User/workspaceStorage/`.
For each subfolder:
1. Read `workspace.json` to get the `folder` URI (the absolute path of
   the project).
2. If the folder path corresponds to a known Halyard project, proceed.

### 2. Session Discovery
Inside a valid workspace folder, Halyard looks for:
- `chatSessions/*.jsonl`: The primary record of chat turns.
- `chatEditingSessions/*/state.json`: The manifest of files modified by
  AI edits.

## Parsing Logic

### Chat Sessions (`*.jsonl`)
The parser iterates over JSON lines to extract:
- **Session UUID:** Filename is the session ID.
- **Timing:** 
  - `start_dt`: Timestamp of the first message.
  - `end_dt`: Timestamp of the last event.
- **Model:** Extracted from turn metadata if available (falls back to
  `github-copilot`).
- **Interaction Counts:**
  - `user_message_count`: Increment on `user.message`.
  - `assistant_message_count`: Increment on `assistant.message`.
  - `tool_calls`: Count `toolRequests` arrays.
- **Tokens:** Sum `completionTokens` values (output tokens).

### Editing Manifest (`state.json`)
The parser reads the `initialFileContents` array to count how many
unique files were involved in the session.
- **Outcome:** `files_touched_count`.

## Privacy Boundary

The parser is **strictly extractive**. 
- It matches on specific keys (`type`, `timestamp`, `completionTokens`,
  `toolRequests`).
- It **NEVER** reads or stores the values of `content`, `reasoningText`,
  or `initialFileContents` (except for counting the number of file URIs).
- No prompt text or code diffs are ever surfaced to the Halyard log.

## Verification

### Phase-0 Spike (Completed)
Confirmed location and schema of `workspaceStorage`, `chatSessions`,
`chatEditingSessions`, and `workspace.json`.

### Automated Tests
- `tests/test_v37_copilot_importer.py`:
  - Mock a VS Code storage directory with fake `workspace.json` and
    `*.jsonl` files.
  - Verify metadata extraction (timing, counts, tokens).
  - Verify correct project attribution.
  - Verify that code/prompt content is NOT present in the resulting
    `AiSession` or log.
