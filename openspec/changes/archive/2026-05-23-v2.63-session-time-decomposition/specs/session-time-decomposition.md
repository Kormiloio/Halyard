# Spec: Session Time Decomposition

## Requirement: Additive optional fields

`AiSession` MUST gain `api_seconds: int | None` and
`tool_seconds: int | None` (default `None`).
`agent_active_seconds` MUST be a derived property = `api + tool`, or
`None` if either part is `None`. It MUST NOT be stored or serialized.

## Requirement: Capture where exposed only

A collector MUST set the fields only from real source timing; absent
⇒ `None`, never `0` or estimated.

### Scenario: Gemini with timing
- GIVEN a Gemini session reporting API 3m25s and tool 18m24s
- THEN `api_seconds=205`, `tool_seconds=1104`,
  `agent_active_seconds=1309`.

### Scenario: collector without timing
- GIVEN a Claude Code session (no API/tool split in payload)
- THEN `api_seconds` and `tool_seconds` are `None`,
  `agent_active_seconds` is `None`, `wall_seconds` unaffected.

### Scenario: partial timing
- GIVEN only `tool_seconds` is available
- THEN `agent_active_seconds` is `None` (not a half-truth).

## Requirement: Backward compatibility & round-trip

Existing log lines (no time tokens) MUST parse with both fields
`None`. A written line MUST round-trip via `parse_sessions`. Older
parsers MUST ignore the new tokens (forward-compatible).

## Requirement: Read-only surface, no judgement

Reports/dashboard/MCP MAY display the durations but MUST NOT compute
an efficiency score or any interpretive metric in this change.
