# Design: v3.12 — VS Code OpenTelemetry collector

## Transport: VS Code pushes, it does not write a file

This is the key difference from the Gemini OTel path (v2.67), which *reads* a
file the CLI writes (`gemini_otel.py`, concatenated pretty-printed JSON).
VS Code Copilot is a standard OTLP **exporter**: it pushes to an endpoint
(`http://localhost:4318` OTLP/HTTP, or `:4317` OTLP/gRPC). So Halyard must
*receive*, not tail.

### Option A (recommended) — minimal local OTLP/HTTP receiver

Halyard runs a tiny OTLP/HTTP receiver bound to `127.0.0.1:4318` that accepts
`POST /v1/traces` (and optionally `/v1/metrics`), parses the OTLP payload, maps
to `AiSession`, appends to the ledger. Hosted inside the existing
`halyard service` launchd process (already a long-lived local daemon for the
dashboard) so there is **no new daemon** for the user to manage — it's another
listener on the same service. VS Code points straight at it.

- Pros: live capture, zero extra moving parts, best UX.
- Cons: Halyard now parses OTLP (protobuf or JSON). Use OTLP/**HTTP+JSON**
  (`github.copilot.chat.otel.exporterType` default is HTTP) to avoid a protobuf
  dependency — JSON OTLP is a documented encoding and keeps the parser
  dependency-light, consistent with the stack.

### Option B (fallback / no-service) — collector file export

User runs a standard OTel Collector with a `file` exporter; Halyard reads that
file (pure v2.67 pattern). No receiver in Halyard, but the user maintains a
collector. Documented as the alternative for users who don't run
`halyard service`.

**Decision:** ship A (receiver in the service). Keep B documented. Both feed the
same span→`AiSession` mapper, which is the testable core.

## GenAI semantic-convention mapping

Copilot OTel follows the OpenTelemetry **GenAI** semantic conventions. The
mapper consumes only metadata attributes (Phase 0 confirms exact keys against a
real capture):

| OTel (GenAI semconv) | AiSession field |
|---|---|
| resource/span `session.id` (or `gen_ai.conversation.id`) | `session_id` |
| `gen_ai.request.model` / `gen_ai.response.model` | `model` (+ `model_breakdown` if multi) |
| `gen_ai.usage.input_tokens` | `input_tokens` (apply `normalise_input`) |
| `gen_ai.usage.output_tokens` | `output_tokens` |
| tool-call child spans (`gen_ai.tool.*` / `execute_tool`) | `tool_calls` (+ `tool_errors` on error status) |
| chat/operation span count | `interaction_count` / `prompt_count` |
| span duration / time-to-first-token | `api_seconds` / TTFT (v2.67 field reuse) |
| span start/end timestamps | `start` / `end` |
| workspace cwd (from resource attrs or config) | project attribution via existing inference |

- `tool` = `"vscode-copilot"` (new advisory slug) **or** reuse
  `"github-copilot"` so existing report/dashboard buckets just work — decide in
  Phase 0; leaning `github-copilot` with `telemetry_source="copilot-otel"` so
  the source is distinguishable from `copilot-jsonl` (the importer) without
  splitting the tool bucket.
- "Unavailable is not zero": any attribute the stream doesn't carry stays
  `None`, never a fabricated 0.

## Session aggregation

Copilot emits many spans per conversation (one per LLM call + tool call). Like
the Gemini `.jsonl` dedup, aggregate **per `session.id`**: sum token usage,
count tool calls, take min(start)/max(end). Because OTLP is pushed
incrementally (spans arrive as the session progresses), the receiver keeps an
in-memory per-session accumulator and **flushes a row** on session end (an
end-of-conversation span/marker) or after an idle TTL (mirror the Windsurf v3.6
TTL-finalization pattern). A flushed session is keyed by `job_id=copilot-otel:
<session.id>` for idempotency.

## Coexistence with the v3.7 importer (no double-count)

Both paths can see the same conversation. Dedup by a shared session key: the
OTel `session.id` and the importer's session id are the same VS Code chat
session id, so:
- OTel row → `job_id=copilot-otel:<id>` (or reuse `copilot:<id>`).
- The importer skips any session already present by that id (extend its dedup
  to recognise the OTel-sourced rows).
- Preference order documented: OTel (live, richer) wins; importer fills gaps
  only for sessions OTel didn't capture (e.g. pre-enablement history).

## Privacy (binding)

- Receiver binds `127.0.0.1` only; never `0.0.0.0`.
- The mapper has an **allowlist** of metadata attribute keys; everything else
  (notably `gen_ai.prompt`, `gen_ai.completion`, message/content events) is
  dropped before anything is constructed — content never enters an `AiSession`.
- A fuzz/contract test feeds spans stuffed with prompt/response/code content
  and asserts none appears in the row, `to_log_line()`, or any `--json` output
  (same discipline as the v3.0/v3.1 privacy fuzz tests).
- Setup writes only the three `github.copilot.chat.otel.*` keys; never enables
  content capture.

## Phase 0 (deferred — built against the documented spec)

The intended gate was: point VS Code at a debug receiver, run one Copilot
agent session, capture a real OTLP payload, confirm exact keys/placement,
then write the mapper.

**Outcome (2026-05-23): the gate could not be run.** The GitHub Copilot
Chat extension is not installed in the build environment (only third-party
`namdang.ollama-copilot-vscode` and `github.codespaces`), and the build
machine has no Copilot license, so no live agent session — and therefore
no real OTLP payload — was obtainable. Owner approved proceeding ("build
now, defer live verify").

Unlike the reverse-engineered internal file format (the thing v3.12
exists to escape), the OTel **GenAI semantic conventions** and the
**OTLP/JSON** encoding are *documented public specs*, so a defensive,
spec-conformant build is meaningfully safer than guessing an undocumented
format. To absorb the residual uncertainty the live capture would have
removed, the mapper is written defensively rather than against a single
assumed shape:

- **`session.id` placement:** probed as **both** a resource attribute
  (`session.id`) **and** a span attribute (`gen_ai.conversation.id` /
  `session.id`). Span attr wins; falls back to resource attr.
- **Usage on spans vs metrics:** tokens are harvested off **spans**
  wherever they appear (`gen_ai.usage.{input,output}_tokens`, plus the
  legacy `prompt`/`completion` aliases). The receiver accepts
  `POST /v1/metrics` with a 200 but does not parse it — re-confirm whether
  Copilot puts per-call usage on metrics during live verification.
- **Session-end signal:** unknown, so finalization relies on the proven
  idle-TTL flush (Windsurf v3.6 pattern, 10-min idle) plus a force-flush
  on service shutdown — not on a Copilot-specific end-marker.
- **"Unavailable is not zero":** any attribute the stream omits stays
  `None`, never a fabricated `0`.

**Re-verification (do before production reliance):** capture one real
payload and confirm the four unknowns above; tighten the allowlist /
classifier if the live keys differ. The mapper is a pure function with
spec-derived fixtures, so re-verification is a fixture diff, not a rewrite.

## As-built decisions (deviations from the original sketch)

- **Receiver is opt-in, not always-on.** The original "host in
  `halyard service`" sketch would start a listener for every user.
  Instead the receiver starts from `run_dashboard` **only when the opt-in
  marker `~/.halyard/vscode-otel.enabled` exists** (written by
  `install-vscode-otel`). A default install gets no new socket — correct
  for a feature gated on unverified live behaviour, and matches the
  proposal's "opt-in" framing. Best-effort: a bind failure is swallowed so
  it can never take down the dashboard service it rides inside.
- **Tool slug:** `tool="github-copilot"` (reuse the existing bucket) with
  `telemetry_source="copilot-otel"`; `job_id="copilot-otel:<session.id>"`.
- **Dedup is two-layered:** the receiver records each captured id into the
  importer's existing dedup-state file (fast path), **and** the importer
  authoritatively scans the target ledger for `job_id=copilot-otel:<id>`
  rows (survives a cleared state file). OTel wins; the importer only fills
  gaps OTel didn't capture.

## Stack / reuse

- Reuse `normalise_input`, `model_breakdown`, project attribution, and the
  `AiSession`/`append_session` write path unchanged.
- Reuse the Windsurf TTL-finalization idea for session flush.
- The HTTP receiver uses the stdlib server already used by the dashboard; no
  new heavy dependency. OTLP/JSON parsed with `json` (no protobuf).
