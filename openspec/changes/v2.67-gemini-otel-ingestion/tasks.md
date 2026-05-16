# v2.67 — Gemini OpenTelemetry Ingestion: Tasks

Status: **IN PROGRESS 2026-05-16.** Phase 0 PASSED — schema verified
from the installed `gemini-cli 0.41.1` bundle source + bundled docs
(no API quota spent); gate outcome **proceed with corrected schema**
(framing is concatenated pretty-printed JSON, `session.id` is a
resource attribute — both recorded in design.md).

- [x] **Phase 0 (BLOCKING):** verified contract recorded in
  design.md. `outfile` supported in 0.41.1; framing = concatenated
  `JSON.stringify(rec,null,2)+"\n"` (NOT line-delimited);
  `gemini_cli.api_response`/`gemini_cli.tool_call` carry int
  `duration_ms`; `session.id` is a **resource** attribute (the join
  key). Gate: **proceed**, reader rewritten to the real schema
- [x] `AiSession`: added `api_seconds`/`tool_seconds` (independent
  optionals); `agent_active_seconds` left unchanged; module-level
  `api_plus_tool_seconds()` display helper (not a property)
- [x] Serializer emits the two tokens only when set; parser reads
  them; helper never serialized; round-trip + forward-compat tested
- [x] `collectors/gemini_otel.py`: bounded fail-closed reader —
  **streaming `json.JSONDecoder().raw_decode`** over the concatenated
  pretty-printed objects (the real framing, not line-split), resource
  -level `session.id` join, sums `duration_ms`, `(None,None)` on any
  fault; `resolve_telemetry_outfile` with Gemini's env→workspace→home
  precedence
- [x] `gemini_cli.handle_agent_stop`: resolves the outfile (relative
  paths joined to cwd), enriches both fields best-effort inside a
  broad guard (a hook must never crash)
- [x] `halyard install-gemini-telemetry` — merges only the four
  managed telemetry keys (foreign keys preserved), `logPrompts:false`
  forced, byte-stable no-op, refuses unparseable / non-object
  telemetry (`HookWriteError`)
- [x] `halyard doctor` nudge: gemini hook on + telemetry off ⇒ one
  `warning` (`telemetry.gemini`), never error — exit code unchanged
- [x] Surface: project-pane "Active Xm (API a · tool b)" line;
  `mcp_server.sessions` includes `api_seconds`/`tool_seconds`
- [x] Tests: `tests/test_v267_gemini_otel.py` (10 cases — real
  framing, resource-level session.id exclusion, unavailable≠0,
  bounded/malformed/oversized, privacy, round-trip+forward-compat,
  install no-op + foreign-key preservation + bad-settings refusal,
  doctor nudge, mcp fields). Updated 2 existing tests for the
  additive surface (doctor "healthy" fixture now includes telemetry;
  mcp key-set assertion)
- [x] `docs/PRD-ai-work-ledger.md` "Session time capture (v2.67)"
  added
- [x] Roadmap entry in `openspec/project.md` (status → complete)

Deviation from design (recorded per spec discipline): Phase 0
verification was done from the **installed gemini-cli 0.41.1 bundle
source + bundled docs** rather than a live `gemini` run — stronger
than one captured sample (it is the implementation itself) and
spends no API quota. It corrected two assumptions: file framing is
concatenated **pretty-printed** JSON (not line-delimited) and
`session.id` is a **resource** attribute (not per-record). Both are
reflected in the reader and the design.md verified-contract section.

## Gate
- [x] `pytest` green (1240 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
