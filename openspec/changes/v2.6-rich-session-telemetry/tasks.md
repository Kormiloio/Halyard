# v2.6 Rich Session Telemetry Tasks

## Data Model

- [x] Add optional rich telemetry fields to `AiSession`.
- [x] Serialize rich fields as optional `key=value` pairs.
- [x] Parse rich fields from existing log lines.
- [x] Preserve backward compatibility with existing logs.
- [x] Sanitize free-form string fields before writing.

## Gemini CLI

- [x] Extend Gemini history summary with rich operational fields.
- [x] Capture `session_id` when available.
- [x] Capture tool call and tool error counts.
- [x] Capture wall, active, API, and tool time when available.
- [x] Capture code added/removed when available.
- [x] Capture compact per-model breakdown when available.
- [x] Omit unavailable fields rather than guessing.

## Reports

- [x] Aggregate tool calls and tool errors.
- [x] Show active agent time where available.
- [x] Label rich telemetry as operational signals, not productivity scores.
- [x] Keep missing telemetry explicit.

## Glass Cockpit

- [x] Add compact rich telemetry display for recent sessions.
- [x] Add warning badge for high tool error rate.
- [x] Show code delta when present.
- [x] Keep layout readable on narrow screens.

## TUI

- [x] Add or extend selected session detail view.
- [x] Show timing breakdown.
- [x] Show tool calls/errors.
- [x] Show code delta.
- [x] Show resume command when present.
- [x] Indicate when rich telemetry is unavailable.

## Tests

- [x] Add parser and serializer coverage for every new field.
- [x] Add backward-compatibility tests for old log lines.
- [x] Add malformed rich-field tests.
- [x] Add Gemini enrichment fixture with rich telemetry.
- [x] Add dashboard rendering tests.
- [x] Add TUI rendering/store tests.

