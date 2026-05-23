# Spec: GitHub Copilot Importer

## Scenario: Retroactive session import
GIVEN a VS Code `workspaceStorage` subfolder with a valid `workspace.json`
AND a `chatSessions/session-uuid.jsonl` file with 3 turns
AND the `session-uuid` is NOT in the `copilot-imported` state file
WHEN `halyard import-copilot` is run
THEN a new `AiSession` MUST be created for the project
AND it MUST have `tool="github-copilot"`
AND it MUST have the correct start/end timestamps from the JSONL
AND it MUST have `assistant_message_count=3`
AND its `output_tokens` MUST equal the sum of `completionTokens`

## Scenario: Automatic project attribution
GIVEN a `workspace.json` containing `"folder": "file:///Users/me/projects/acme-auth"`
AND `/Users/me/projects/acme-auth/halyard.toml` exists with `slug="acme:auth"`
WHEN the session is imported
THEN the `AiSession.project` MUST be set to `"acme:auth"`

## Scenario: Counting files touched in edits
GIVEN a `chatEditingSessions/uuid/state.json` file
AND its `initialFileContents` array contains 5 unique file URIs
WHEN the corresponding chat session is imported
THEN the `AiSession.files_touched_count` MUST be set to 5

## Scenario: Privacy boundary enforcement
GIVEN a `chatSessions/*.jsonl` file containing prompt text and reasoning strings
WHEN the session is parsed
THEN the resulting `AiSession` and the log line MUST NOT contain any of the
original text
AND only the numeric metadata (tokens, counts, IDs) MUST be preserved

## Scenario: Idempotent import
GIVEN a session ID that is already present in `~/.halyard/copilot-imported`
WHEN `halyard import-copilot` is run
THEN that session MUST NOT be imported again
AND no duplicate log records MUST be created
