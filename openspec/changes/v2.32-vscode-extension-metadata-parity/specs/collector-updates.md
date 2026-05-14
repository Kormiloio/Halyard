# Spec: Collector Metadata Updates

## Requirement: Claude Code metadata parity

The Claude Code collector SHOULD populate shared metadata fields when hook
payloads or transcript event structure expose safe counts.

### Scenario: transcript contains assistant events

WHEN Claude Code provides a local transcript path
THEN Halyard MAY count assistant events and token usage
AND MUST NOT persist prompt text, assistant text, code, filenames, or transcript
content.

### Scenario: git metadata is available

WHEN the collector can read branch, commits, and code delta
THEN it writes branch, commit count, code added, and code removed using the
shared fields.

## Requirement: Cursor metadata parity

The Cursor collector SHOULD populate shared metadata fields from public hook
payloads and workspace metadata.

### Scenario: workspace roots are present

WHEN Cursor sends `workspace_roots`
THEN Halyard uses them for attribution and git metadata
AND MUST NOT persist full workspace paths in `ai-sessions.log`.

### Scenario: interaction counts are absent

WHEN Cursor does not expose interaction counts
THEN Halyard leaves interaction fields unavailable
AND MUST NOT infer fake zeroes.

## Requirement: Gemini CLI metadata parity

The Gemini CLI collector SHOULD normalize existing rich telemetry into the
shared metadata vocabulary.

### Scenario: history exposes tool calls and errors

WHEN Gemini history contains tool call and error counts
THEN Halyard writes `tool_calls` and `tool_errors`
AND reports can aggregate them across tools.

### Scenario: history exposes model breakdown

WHEN Gemini history contains multiple models
THEN Halyard writes a compact `model_breakdown`
AND sets the primary model to the dominant model by output token count.

### Scenario: history exposes message counts

WHEN Gemini history exposes safe message or interaction counts
THEN Halyard writes the shared interaction fields
AND does not persist message content.

## Requirement: Codex Desktop metadata parity

The Codex Desktop importer SHOULD populate shared metadata fields from JSONL
event types when available.

### Scenario: JSONL contains token snapshots

WHEN a Codex JSONL file contains token count events
THEN Halyard records token metadata
AND marks token availability accurately.

### Scenario: JSONL contains conversation events

WHEN a Codex JSONL file contains event types that can be counted
THEN Halyard MAY write interaction counts
AND MUST NOT persist message payload text.

## Requirement: VS Code metadata parity

VS Code extension records SHOULD use the same fields as other collectors.

### Scenario: extension records a session

WHEN the VS Code extension records a session
THEN Halyard writes `tool=vscode` or a more specific supported tool slug
AND writes `source=vscode-extension`
AND includes available shared metadata fields.

### Scenario: Copilot token cost is unavailable

WHEN Copilot token or cost data is unavailable
THEN Halyard marks token data unavailable or records user-provided estimates
with manual trust
AND MUST NOT claim captured per-token cost.

