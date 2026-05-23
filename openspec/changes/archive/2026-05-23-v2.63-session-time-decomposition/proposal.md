# v2.63 — Session Time Decomposition

## Problem

Halyard models only `wall_seconds` (session span). The tools' own
summaries expose a far richer time picture — Gemini CLI's `/quit`:

```
Wall Time:    14h 4m 49s
Agent Active: 21m 50s
  » API Time: 3m 25s (15.7%)
  » Tool Time: 18m 24s (84.3%)
```

"84% of agent-active time was tool execution, not model inference" is
exactly the *work-intelligence* depth Halyard's thesis promises and a
single-tool dashboard cannot give across tools/projects. Today we
throw it away.

## Goal

Model and capture the active-time decomposition where a collector
exposes it.

- New `AiSession` fields: `api_seconds: int | None`,
  `tool_seconds: int | None`. `agent_active_seconds` is **derived**
  (`api + tool`) — not stored, to avoid an inconsistent third field.
  `wall_seconds` stays as-is.
- Collectors populate `api_seconds`/`tool_seconds` when the source
  provides them (Gemini `/quit` summary, Codex rollout timing if
  present); `None` otherwise.
- Surfaced read-only in reports/dashboard as an "active time" line and
  an api-vs-tool split; never required, never inferred.

## Constraints honored

- **Additive schema.** Two new optional fields with `None` default;
  old log lines parse unchanged; new tokens are ignored by older
  parsers.
- **Unavailable is not zero.** No timing in the source ⇒ `None`;
  derived agent-active is `None` unless both parts exist.
- **Derived, not duplicated.** `agent_active_seconds` is a computed
  property, not a stored field, so it cannot disagree with its parts.
- **Capture-only privacy.** Durations only; no content.

## Non-goals

- Reconstructing API/tool time for collectors that don't report it
  (no estimation — that would be a fabricated metric).
- Per-tool-call latency histograms (future, separate).

## Out of scope

Wall-vs-active "efficiency score" or any derived judgement metric —
this change captures and displays raw durations only; interpretation
is a later product decision.
