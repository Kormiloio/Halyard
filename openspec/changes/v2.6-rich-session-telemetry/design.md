# v2.6 Rich Session Telemetry Design

## Data Model

Extend `AiSession` with optional metadata fields. The parser must accept missing
fields and old log lines without behavior changes.

Recommended dataclass additions:

```python
session_id: str | None = None
tool_calls: int | None = None
tool_success: int | None = None
tool_errors: int | None = None
success_rate: float | None = None
user_agreement: float | None = None
code_added: int | None = None
code_removed: int | None = None
wall_seconds: int | None = None
agent_active_seconds: int | None = None
api_seconds: int | None = None
tool_seconds: int | None = None
resume_command: str | None = None
model_breakdown: str | None = None
```

## Serialization

Rich fields use the existing `key=value` extension mechanism.

Integer and float fields serialize directly. String fields must be sanitized:

- no spaces;
- no newlines;
- no tabs;
- no raw prompt or code content;
- shell commands should be compact and safe to display.

For complex data such as per-model breakdowns, prefer a compact safe encoding
that remains readable enough for local inspection. If the data becomes too
complex, store summary tags first and defer structured sidecar files to a later
change.

## Gemini CLI Collector

The Gemini collector already enriches hook data from the local Gemini history
file. Extend the history parser summary with any available operational fields:

- session id;
- total tool calls;
- total tool errors;
- per-model request and token breakdown;
- code additions and deletions;
- wall time;
- agent active time;
- API time;
- tool time;
- resume command if it can be safely derived.

When fields are unavailable, omit them.

## Work-Health Signals

Derived labels can be computed in reports/UI without writing them to the raw log.

Initial examples:

- `tool_errors > 0`;
- `tool_errors / tool_calls >= 0.10`;
- `wall_seconds` much greater than `agent_active_seconds`;
- `code_added + code_removed` unusually high for a short session;
- unattributed sessions with rich telemetry.

These labels should be phrased as "signals" or "needs review," not judgments.

## UI

### Glass Cockpit

Add compact columns or badges to recent sessions:

- calls/errors;
- active time;
- code delta;
- session health badge.

Avoid crowding the existing dashboard. Use detail rows or small badges rather
than widening every table excessively.

### TUI

Add a session detail panel or expand the selected session view. The TUI is the
better place for detailed fields because it already supports selection and
navigation.

## Backward Compatibility

Existing logs remain valid.

Old Halyard versions should ignore unknown `key=value` fields, which is already
the expected extension behavior.

## Testing

Tests should cover:

- serialization and parsing of every new field;
- old log lines without rich fields;
- malformed numeric rich fields;
- Gemini history enrichment when rich fields are present;
- Gemini history enrichment fallback when they are absent;
- dashboard rendering with and without rich telemetry;
- TUI store/session detail rendering with and without rich telemetry.

