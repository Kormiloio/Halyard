# Spec: Parse-Time Synthetic-Telemetry Guard

## Requirement: Recognize the canned fingerprint

`session_is_synthetic_telemetry(session)` MUST return True iff **all**
of: `cost_usd == 0`, project is falsy, and `(input_tokens,
output_tokens, model)` is exactly `(2000, 400, "claude-3.5-sonnet")`
or `(100, 50, "gemini-2.0-pro")`. Otherwise False.

### Scenario: exact Cursor fingerprint
- GIVEN a session 2000/400, `claude-3.5-sonnet`, cost 0, no project
- THEN the predicate is True.

### Scenario: nonzero cost is real
- GIVEN the same tokens/model but cost 1.20
- THEN the predicate is False.

### Scenario: attributed is real
- GIVEN the same tokens/model/cost 0 but project `kormilo:halyard`
- THEN the predicate is False.

### Scenario: current model is real
- GIVEN 2000/400, `claude-opus-4-7`, cost 0, no project
- THEN the predicate is False.

## Requirement: Excluded from every read path

`ai_log.parse_sessions` MUST omit synthetic-telemetry rows from its
returned list. Because all surfaces (CLI, dashboard, aggregate, MCP)
read through `parse_sessions`, none may surface these rows.

### Scenario: mixed log
- GIVEN an `ai-sessions.log` with 2 synthetic and 2 genuine `s` lines
- WHEN `parse_sessions` reads it
- THEN exactly the 2 genuine sessions are returned.

### Scenario: aggregate/MCP inherits exclusion
- GIVEN the same log reachable by the aggregate layer
- WHEN the MCP `work_summary` / dashboard state is built
- THEN synthetic rows contribute zero sessions and zero cost.

## Requirement: No deletion, no mutation

The raw synthetic `s` lines MUST remain byte-for-byte in
`ai-sessions.log` after `parse_sessions` runs (exclusion is read-only;
no quarantine write, no rewrite).

### Scenario: file untouched
- GIVEN a log with synthetic lines
- WHEN `parse_sessions` is called (even repeatedly)
- THEN the file content is byte-identical afterward.

## Requirement: Write-path defence in depth

The Claude Code, Cursor, and Gemini collector stop-handlers MUST also
refuse to write a session matching the synthetic fingerprint, so
Halyard's own collectors never emit it.
