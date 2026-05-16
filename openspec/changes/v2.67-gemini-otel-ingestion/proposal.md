# v2.67 — Gemini OpenTelemetry Ingestion (api/tool time)

## Problem

v2.63 (session time decomposition) was **deferred** after its Phase 0
audit: Gemini's `/quit` `API · Tool` time split is computed in memory
and rendered to the terminal only. It is **not** in the chat session
JSON (timestamps but no durations), **not** in `logs.json`, and **not**
in any hook payload. A timestamp-only reconstruction would require
heuristically attributing inter-event gaps — estimation, an explicit
non-goal.

The audit also found the one *plausible* source: Gemini CLI's
**opt-in OpenTelemetry**. The working hypothesis is that with
`telemetry.target = "local"` + `telemetry.outfile`, Gemini writes OTLP
records carrying true, measured api- and tool-call `duration_ms`
joinable by session — exactly the api/tool split v2.63 wanted,
captured not estimated. **This schema is not yet verified** (no OTEL
is configured on the dev machine); a mandatory Phase 0
verify-before-build gate (see design.md) confirms the real format
first and **defers the change** if Gemini provides no usable
file/session-keyed signal — the same discipline that correctly
deferred v2.63. It is a different ingestion model (an OTLP file, not
a session-end summary) and so deserves its own changeset rather than
being smuggled into v2.63.

## Goal

Capture real Gemini api-time / tool-time from the user's opt-in OTLP
outfile, and land the additive schema v2.63 needed — **without** the
breaking change v2.63's design contained.

- Add `api_seconds: int | None` and `tool_seconds: int | None` to
  `AiSession` as **independent optional fields**.
  `agent_active_seconds` stays the existing **stored** field (used by
  `work_health` + `record-session`); it is **not** converted to a
  derived property (that was v2.63 design Conflict 1 — a breaking
  change to existing logs/CLI/health). A separate read-only derived
  helper `api_plus_tool_seconds` is exposed for display only.
- New OTLP-outfile reader: for the session being finalised, sum
  `gemini_cli.api_response.duration_ms` → `api_seconds` and
  `gemini_cli.tool_call.duration_ms` → `tool_seconds`, joined by
  `session.id`. Absent/disabled ⇒ both `None`.
- Opt-in, explicit: a `halyard install-gemini-telemetry` command
  configures the `telemetry` block (proposed with a diff, never a
  silent write), and `halyard doctor` nudges when the Gemini hook is
  active but telemetry is off (warn-only, exit-code contract
  preserved).
- Surface read-only: session detail shows `active Xm (API a · tool b)`
  when both parts exist; `mcp_server.sessions` includes the two
  fields.

## Constraints honored

- **Opt-in / no silent writes.** Halyard never enables Gemini
  telemetry implicitly; the install command shows a config diff and
  waits for approval (non-negotiable #4).
- **Unavailable is not zero.** No outfile, telemetry off, or no
  matching `session.id` ⇒ `api_seconds`/`tool_seconds` stay `None`,
  never `0`.
- **Capture-only privacy.** Only `duration_ms`, counts, model, and
  `session.id` are read. Prompt/response/tool-arg content is ignored
  even if the user set `telemetry.logPrompts = true` (non-negotiable
  #5).
- **Additive, backward compatible.** Two new optional fields; old log
  lines parse unchanged; older parsers ignore the new tokens.
  `agent_active_seconds` semantics and serialization are untouched.
- **Bounded untrusted read.** The outfile is user-controlled but
  attacker-influenceable in principle; reuse the v2.39 input-bound
  pattern (size cap, streamed parse, fail-closed to `None`).

## Non-goals

- Converting/removing `agent_active_seconds` (explicitly rejected —
  v2.63 Conflict 1).
- `target: "gcp"`, running an OTLP collector daemon, or real-time
  streaming. Only the local **file** exporter is read.
- api/tool time for Claude Code, Cursor, or Codex (Codex
  `tool_seconds` from begin/end spans may be a later, separate
  follow-up; not here).
- Per-tool latency histograms or any efficiency/judgement score
  (v2.63's non-goal carries over).

## Out of scope

A generic multi-tool OTEL pipeline. This change reads the Gemini CLI
OTLP file schema specifically; generalisation waits until a second
emitter exists (same discipline as the public `ai-sessions.log` spec).
