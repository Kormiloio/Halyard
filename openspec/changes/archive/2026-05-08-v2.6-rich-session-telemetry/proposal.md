# v2.6 Rich Session Telemetry

## Summary

Extend Halyard's AI session model beyond tokens and cost so local reports,
Glass Cockpit, and the TUI can show richer work-health metadata from agentic AI
tools.

The first target is Gemini CLI's shutdown-style summary data: session id, tool
call counts, tool errors, wall time, agent active time, API/tool time, code
delta, and per-model breakdowns where available.

## Motivation

AI-assisted work is becoming more agentic. Tokens and dollars explain spend, but
they do not explain whether a session was smooth, noisy, blocked, or productive.

Modern AI tools often expose operational metadata:

- tool calls;
- tool failures;
- user approvals or agreement;
- code additions and deletions;
- wall time versus active agent time;
- per-model request and token breakdowns;
- resume commands.

Capturing this metadata locally lets Halyard move from cost tracking toward AI
work intelligence while preserving its privacy posture. The default capture
remains metadata-only. Prompts, conversation content, and source code are still
out of scope.

## Goals

- Add optional rich telemetry fields to `AiSession`.
- Preserve backward compatibility with existing `ai-sessions.log` lines.
- Capture available Gemini CLI session summary fields from history enrichment.
- Display work-health indicators in Glass Cockpit and TUI session detail views.
- Keep uncertainty explicit when a tool does not expose a field.
- Avoid prompt, transcript, or source code capture.

## Non-Goals

- Do not capture prompts, conversations, or source code.
- Do not claim exact productivity or ROI from metadata alone.
- Do not require all collectors to expose the same rich fields.
- Do not change the plain-text log as source of truth.
- Do not introduce a cloud dependency.

## Proposed Fields

Optional session fields:

```text
session_id=<string>
tool_calls=<int>
tool_success=<int>
tool_errors=<int>
success_rate=<float>
user_agreement=<float>
code_added=<int>
code_removed=<int>
wall_seconds=<int>
agent_active_seconds=<int>
api_seconds=<int>
tool_seconds=<int>
resume_command=<safe-string>
model_breakdown=<safe-string>
```

All fields are optional and collector-dependent.

## Product Surfaces

### Local Log

The plain-text `ai-sessions.log` format remains append-only and backwards
compatible. Rich fields are appended as additional `key=value` pairs.

### Glass Cockpit

Glass Cockpit should show a compact work-health summary for recent sessions:

- tool calls;
- tool errors;
- active time versus wall time;
- code delta;
- warning state for high error rates or missing attribution.

### TUI

The TUI should expose richer session detail:

- session id;
- timing breakdown;
- model breakdown;
- tool call success/failure;
- code delta;
- resume command when present;
- trust/source indicators for missing fields.

### Reports

Reports may aggregate:

- total tool calls;
- tool error rate;
- active agent time;
- code additions and deletions;
- sessions with missing telemetry.

Aggregates should be labeled as operational signals, not productivity scores.

## Risks

- Some fields may be unavailable or unstable across tool versions.
- Code delta can be misleading without context.
- Work-health signals can be misused as surveillance if shown without care.
- Long `key=value` fields could make log lines harder to read.

## Privacy Notes

This change captures metadata only. `resume_command` must not include prompt
content. Any field with free-form text must be sanitized into a safe tokenized
value or omitted.

Sensitive content capture remains out of scope and would require a separate
explicit opt-in design.

