# v2.67 — Gemini OpenTelemetry Ingestion: Design

> Spec only — proposed, not started. Supersedes the schema portion of
> the deferred v2.63 with a non-breaking shape.

## Phase 0 — Verify-before-build gate (MANDATORY, blocks all code)

**Lesson from v2.63:** that change was deferred because it assumed a
Gemini data source's shape. The OTLP schema below
(`gemini_cli.api_response`/`gemini_cli.tool_call` events, `duration_ms`,
`session.id` join key, line-delimited JSON file exporter) is currently
an **assumption, not a verified fact** — there is no OTEL configured on
this machine, and exact event/attribute names + the session join key
(resource attribute vs log-record attribute) + whether the *installed*
Gemini CLI version even supports `telemetry.outfile` are all unknown.

Before writing any reader/collector code, an implementer MUST:

1. Enable Gemini telemetry to a local file (`telemetry.enabled=true`,
   `target="local"`, `outfile=<tmp path>`) on a real Gemini CLI run.
2. Capture one real outfile and record, in this design doc, the
   **actual**: file framing (line-delimited JSON? OTLP/JSON proto?),
   the exact event/log names, where `duration_ms` (or equivalent)
   lives, and the exact field that carries the session id and at what
   level (resource vs scope vs record).
3. Confirm a session-level join is possible between those records and
   the `session_id` the Gemini collector already has.

**Gate outcome:**
- Schema matches the assumptions → proceed; replace the "assumed"
  language below with the verified contract.
- Schema differs but is still session-joinable → rewrite the reader
  section to the real schema, then proceed.
- Installed Gemini CLI has no `outfile` / no usable session key, or
  the only path is a running collector daemon → **defer v2.67** (same
  disposition as v2.63); do not build a reader against an assumed
  format.

Everything below is the *intended* design conditional on Phase 0
confirming the schema.

## Schema (`ai_log.py`)

Add two independent optional fields next to `wall_seconds`:

```python
api_seconds: int | None = None
tool_seconds: int | None = None
```

`agent_active_seconds` (existing stored field, `:261`) is **left
exactly as-is** — still stored, serialized, parsed, written by
`record-session --agent-active-seconds`, read by `work_health`. No
behaviour change, no data migration.

Display-only helper (module function, *not* an `AiSession` property,
so it can never be mistaken for stored state):

```python
def api_plus_tool_seconds(s: AiSession) -> int | None:
    if s.api_seconds is None or s.tool_seconds is None:
        return None
    return s.api_seconds + s.tool_seconds
```

Serialization: emit `api_seconds=`/`tool_seconds=` only when not
`None`; two new parser `case` arms reading ints. Old lines → both
`None`. Round-trip + forward-compat (older parser ignores unknown
tokens) covered by tests.

## OTLP outfile reader (`collectors/gemini_otel.py`)

**ASSUMED schema — must be replaced with Phase 0's verified contract
before implementation.** Working hypothesis: Gemini CLI with
`telemetry.target="local"` + `telemetry.outfile=<path>` writes OTLP
records to that file (assumed one JSON object per line, file exporter
form), with signals:

- `gemini_cli.api_response` event — attrs incl. `duration_ms`,
  `model`, token counts; `session.id` (level TBD: resource vs record).
- `gemini_cli.tool_call` event — attrs incl. `function_name`,
  `duration_ms`, `success`; `session.id`.

Reader contract (shape stable regardless of exact schema):

- Input: the configured outfile path + the target `session_id`.
- Bounded read (v2.39 pattern): resolve path, regular-file only, size
  cap, streamed line parse; any malformed line skipped; any fatal
  issue ⇒ return `(None, None)`.
- Aggregate for the matching session only:
  `api_seconds = round(Σ api duration_ms / 1000)`,
  `tool_seconds = round(Σ tool duration_ms / 1000)`. `duration_ms` is
  summed per record (multiple API calls / tool calls per session add
  up; retries/streaming count as captured time — honest, not
  estimated). The session-id match MUST handle whichever level Phase 0
  finds it at (resource attribute and/or record attribute).
- No matching records ⇒ `(None, None)` (unavailable is not zero).
- Content fields (`function_args`, prompt/response text) are never
  read, even if present.

## Collector wiring (`gemini_cli.py`)

In `handle_agent_stop`, after the session is otherwise built and the
`session_id` is known: resolve the telemetry outfile from Gemini
settings (`~/.gemini/settings.json` and workspace `.gemini/
settings.json`, workspace wins). If configured, call the reader with
that `session_id`; set `api_seconds`/`tool_seconds` when returned.
Best-effort: any exception ⇒ leave both `None` (a hook must never
crash). No new dependency — OTLP file form is plain JSON lines, parsed
with `json`.

## Opt-in helpers

- `halyard install-gemini-telemetry` — adds/updates the `telemetry`
  block (`enabled:true`, `target:"local"`, `outfile:<~/.halyard/
  gemini-otel.log>`, `logPrompts:false`) using the same no-clobber /
  diff-and-approve machinery as `install-gemini-hook` (v2.45/v2.51
  pattern: byte-stable no-op, foreign keys preserved). Never silent.
- `halyard doctor` — when the Gemini hook is installed but telemetry
  is off, emit a `warn` (never `error`) with the one-line fix. Flows
  through `DoctorReport` so dashboard/TUI inherit it (v2.52 pattern).

## Surface

- Reports / dashboard session detail: `active Xm (API a · tool b)`
  line when `api_plus_tool_seconds(s) is not None`.
- `mcp_server.sessions`: include `api_seconds`/`tool_seconds`
  (metadata only — already the contract).
- No aggregate metric, no efficiency score (v2.63 non-goal carried).

## Tests (`tests/test_v267_gemini_otel.py`)

1. OTLP fixture with api + tool records for a session id → reader
   returns the summed seconds; non-matching `session.id` excluded.
2. Collector end-to-end: gemini stop with a configured outfile →
   `AiSession.api_seconds`/`tool_seconds` set; `agent_active_seconds`
   untouched.
3. Telemetry off / no outfile / file absent → both `None`,
   `wall_seconds` unaffected.
4. Malformed / oversized / partial OTLP lines → `(None, None)`,
   no crash (bounded-read invariant).
5. Privacy: a fixture with `logPrompts:true` content present → reader
   never surfaces any text field.
6. Round-trip: write → `parse_sessions` → equal; old line without the
   tokens parses (both `None`); `agent_active_seconds` round-trips
   unchanged.
7. `install-gemini-telemetry` no-op is byte-stable; foreign settings
   keys preserved; refuses to clobber an unparseable settings file
   (v2.41 `HookWriteError` pattern).
8. `doctor` nudge: hook on + telemetry off ⇒ one `warn`, exit code
   unchanged.
9. `mcp_server.sessions` exposes the two fields.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Feature changeset (new schema + new collector path + new
command) — full spec, not bug-class.

## Relationship to v2.63

This changeset delivers v2.63's *intent* for Gemini via the only real
data source, and lands v2.63's two schema fields in a **non-breaking**
form (independent optionals; `agent_active_seconds` preserved). v2.63
stays deferred and is effectively superseded for the Gemini case; its
design.md Phase 0 audit is the authoritative record of why.
