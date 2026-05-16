# Spec: Gemini OpenTelemetry Ingestion

> Precondition: the design.md Phase 0 verify-before-build gate MUST
> pass (real Gemini OTLP outfile captured and its schema recorded)
> before any requirement below is implemented. If Phase 0 finds no
> usable file/session-keyed signal, the change is deferred and these
> requirements do not apply.

## Requirement: Additive optional time fields (non-breaking)

`AiSession` MUST gain `api_seconds: int | None` and
`tool_seconds: int | None` (default `None`). `agent_active_seconds`
MUST remain a stored, serialized, parsed field with unchanged
semantics — it MUST NOT be removed or converted to a derived
property. A display-only `api_plus_tool_seconds(session)` helper MUST
return `api_seconds + tool_seconds`, or `None` if either is `None`,
and MUST NOT be stored or serialized.

### Scenario: old log line
- GIVEN an `ai-sessions.log` line written before v2.67
- THEN it parses with `api_seconds=None`, `tool_seconds=None`, and its
  `agent_active_seconds` value (if any) is preserved unchanged.

### Scenario: round-trip
- GIVEN a session with `api_seconds=205`, `tool_seconds=1104`
- WHEN written and re-parsed
- THEN the parsed session equals the original; older parsers ignore
  the two unknown tokens.

## Requirement: Capture only from real OTLP timing

The Gemini collector MUST set `api_seconds`/`tool_seconds` only by
summing measured `duration_ms` from the user's opt-in OTLP outfile,
matched by `session.id`. It MUST NOT estimate, infer from
inter-event gaps, or default to `0`.

### Scenario: telemetry enabled with matching records
- GIVEN Gemini telemetry `target:"local"` with an outfile containing
  `gemini_cli.api_response` records summing 205000 ms and
  `gemini_cli.tool_call` records summing 1104000 ms for this
  `session.id`
- THEN `api_seconds=205`, `tool_seconds=1104`,
  `api_plus_tool_seconds=1309`.

### Scenario: telemetry disabled or no outfile
- GIVEN the Gemini hook ran but telemetry is off or no outfile is
  configured
- THEN `api_seconds` and `tool_seconds` are `None`,
  `api_plus_tool_seconds` is `None`, `wall_seconds` unaffected.

### Scenario: no matching session id
- GIVEN an outfile that contains only records for other sessions
- THEN both fields are `None` (not `0`).

### Scenario: partial signal
- GIVEN api_response records exist but no tool_call records for the
  session
- THEN `api_seconds` is set, `tool_seconds` is `None`, and
  `api_plus_tool_seconds` is `None` (no half-truth total).

## Requirement: Bounded, fail-closed untrusted read

The outfile MUST be read under the v2.39 input-bound contract:
regular-file only, size-capped, streamed parse. Any malformed line is
skipped; any fatal condition yields `(None, None)` and MUST NOT crash
the hook.

## Requirement: Capture-only privacy

The reader MUST consume only `duration_ms`, counts, model, and
`session.id`. It MUST NOT read or surface prompt, response, or
tool-argument content, even when `telemetry.logPrompts = true`.

## Requirement: Opt-in, no silent writes

Halyard MUST NOT enable Gemini telemetry implicitly.
`halyard install-gemini-telemetry` MUST propose the `telemetry`
config change as an approvable diff, be a byte-stable no-op when
already configured, preserve foreign settings keys, and refuse to
clobber an unparseable settings file. `halyard doctor` MUST emit a
`warning` (never `error`) when the Gemini hook is active but telemetry
is off, with the exact one-line fix; the exit-code contract is
preserved.

## Requirement: Read-only surface, no judgement

Reports/dashboard/MCP MAY display the durations but MUST NOT compute
an efficiency score or any interpretive metric in this change.
`mcp_server.sessions` MUST include `api_seconds`/`tool_seconds`.
