# v2.67 — Gemini OpenTelemetry Ingestion: Design

> Phase 0 PASSED 2026-05-16 (gate outcome: **proceed with corrected
> schema**). Verified against the installed `gemini-cli 0.41.1` from
> its own bundle source + bundled telemetry docs — no API quota spent.
> Supersedes the schema portion of the deferred v2.63 with a
> non-breaking shape.

## Phase 0 — VERIFIED CONTRACT (gemini-cli 0.41.1, 2026-05-16)

Verification method: rather than a live `gemini` run (which would
spend the user's API quota and need interactive auth), the contract
was read from the ground-truth installed source — the bundled
`docs/cli/telemetry.md` (authoritative event/attribute reference for
this exact version) and the bundled `FileExporter`/telemetry-init
code. This is stronger than one captured sample because it is the
implementation itself, not an inferred shape.

**Findings vs the original assumptions:**

| Aspect | Assumed | **Verified (0.41.1)** |
|---|---|---|
| `outfile` support | hoped | **YES** — `telemetry.{enabled:true,target:"local",outfile:<path>}` or `GEMINI_TELEMETRY_OUTFILE`; overrides `otlpEndpoint`. Doc example uses `.gemini/telemetry.log` |
| File framing | "one JSON object per line" | **WRONG** — `createWriteStream(path,{flags:"a"})`, each record `JSON.stringify(rec,null,2)+"\n"`. File = concatenated **pretty-printed multi-line** JSON objects. Line-by-line parsing is impossible; need a streaming JSON-object decoder |
| Event names | `gemini_cli.api_response` / `gemini_cli.tool_call` | **CONFIRMED** (both present, both carry `duration_ms` int) |
| `duration_ms` | int on the event | **CONFIRMED** — int attribute on each event log record |
| `session.id` join level | "resource and/or record, TBD" | **RESOURCE attribute** — `resourceFromAttributes({...,"session.id":config.getSessionId()})` (chunk-NET4RIEQ.js:250642). Not a per-record attribute |
| Privacy | content separate | **CONFIRMED** — text lives in distinct attrs (`request_text`/`response_text`/`gen_ai.*`); `logPrompts` **defaults `true`** in 0.41.1, so install MUST force `logPrompts:false` and the reader MUST ignore content regardless |

**Gate outcome:** schema differs (framing + session.id level) but is
fully session-joinable ⇒ per the gate, the reader section below is
rewritten to the real schema and the change **proceeds**.

## Phase 0 — original verify-before-build gate (kept for the record)

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

## OTLP outfile reader (`collectors/gemini_otel.py`) — VERIFIED schema

Gemini CLI 0.41.1 with `telemetry.target="local"` +
`telemetry.outfile=<path>` writes OTLP **log records** to that file
via `FileLogExporter`, each as `JSON.stringify(record, null, 2)`
followed by `"\n"`, appended. The file is therefore a **stream of
concatenated pretty-printed JSON objects** (multi-line, 2-space
indent) — *not* line-delimited. Signals of interest:

- `gemini_cli.api_response` log record — `attributes.duration_ms`
  (int), `attributes.model`, token counts; the event name is the
  record body/eventName.
- `gemini_cli.tool_call` log record — `attributes.duration_ms` (int),
  `attributes.function_name`, `attributes.success`.
- `session.id` is a **resource** attribute
  (`record.resource.attributes["session.id"]`), shared by every
  record in that process — the join key.

OTel JS `ReadableLogRecord` serialized via `JSON.stringify` yields
(observed shape): top-level `body`/`severityText`, `attributes`
(object), and `resource` carrying `attributes` (or `_attributes` /
`_rawAttributes` depending on SDK internals). The reader probes the
known resource-attribute container variants and the event name under
`body` / `eventName` / `attributes["event.name"]` defensively, since
those are SDK-internal serialization details rather than a documented
contract.

Reader contract:

- Input: the configured outfile path + the target `session_id`.
- Bounded read (v2.39 pattern): resolve real path, regular-file only,
  enforce a size cap (`_MAX_OTEL_BYTES`), read capped bytes, decode
  with a **streaming `json.JSONDecoder().raw_decode`** loop over the
  buffer (skip inter-object whitespace; on a decode error advance to
  the next `{` and continue; never raise). Any fatal issue ⇒
  `(None, None)`.
- Match only records whose resource `session.id` == target
  `session_id`. For matched records sum by event name:
  `api_seconds = round(Σ api_response.duration_ms / 1000)`,
  `tool_seconds = round(Σ tool_call.duration_ms / 1000)`.
  `duration_ms` is summed per record (multiple API/tool calls per
  session add up; retries/streaming count as captured time — honest,
  not estimated).
- A kind with **zero** matching records stays `None` for that kind
  (unavailable is not zero); both `None` if nothing matches.
- Content fields (`function_args`, `request_text`, `response_text`,
  `gen_ai.input.messages`, `gen_ai.output.messages`, …) are **never
  read or returned**, even when `logPrompts:true` put them in the
  file.

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

1. OTLP fixture in the **real framing** (concatenated pretty-printed
   multi-line JSON objects, resource-level `session.id`) with api +
   tool records for a session id → reader returns the summed seconds;
   records whose resource `session.id` differs are excluded.
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
