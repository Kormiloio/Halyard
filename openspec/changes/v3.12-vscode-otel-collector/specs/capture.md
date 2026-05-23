# Spec: VS Code Copilot OTel capture

## Requirement: ingest VS Code Copilot OpenTelemetry locally

Halyard SHALL capture VS Code Copilot agent sessions from the OpenTelemetry
stream VS Code emits, via a local OTLP endpoint, without reading VS Code's
internal storage.

### Scenario: a Copilot session becomes a ledger row

- WHEN OTel is enabled in VS Code pointing at Halyard's local receiver
- AND a Copilot agent session runs and ends
- THEN one `AiSession` row is recorded (no manual import) with `session_id`,
  `model`, `input_tokens`, `output_tokens`, `tool_calls`, `interaction_count`,
  and duration, attributed to the workspace's project.

### Scenario: survives an internal-storage layout change

- WHEN VS Code relocates or renames its internal chat-session files
- THEN OTel capture is unaffected (it does not read internal storage).

### Scenario: receiver is local-only

- WHEN the OTLP receiver starts
- THEN it binds `127.0.0.1` only and rejects non-local connections.

## Requirement: metadata only, never content

Capture SHALL be limited to metadata; prompt, response, and code content SHALL
never be recorded.

### Scenario: content attributes are dropped

- WHEN an OTLP span carries `gen_ai.prompt`, `gen_ai.completion`, message
  content events, or any non-allowlisted attribute
- THEN none of that content appears in the `AiSession`, `to_log_line()` output,
  or any `--json` surface (asserted by a fuzz/contract test).

## Requirement: no double-count with the importer

The OTel path and the v3.7 importer SHALL NOT both record the same session.

### Scenario: importer skips an OTel-captured session

- WHEN a session is already recorded via OTel (`job_id` carries its session id)
- THEN `halyard import-copilot` skips that session.

## Requirement: opt-in setup and discoverability

### Scenario: install wires VS Code to the receiver

- WHEN the user runs `halyard install-vscode-otel`
- THEN the three `github.copilot.chat.otel.*` settings are written (after a
  diff-and-approve), pointing VS Code at the local receiver, and content
  capture is left disabled.

### Scenario: doctor nudges when unwired

- WHEN VS Code Copilot history exists on disk but OTel capture is not configured
- THEN `halyard doctor` emits a `warning` (never `error`) with the one-line fix.

## Requirement: session aggregation and finalization

### Scenario: many spans, one row

- WHEN a conversation emits multiple LLM-call and tool-call spans under one
  `session.id`
- THEN they aggregate into a single row (summed tokens, counted tools,
  min start / max end), flushed on session end or after an idle TTL.
