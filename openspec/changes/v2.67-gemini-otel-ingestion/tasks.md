# v2.67 — Gemini OpenTelemetry Ingestion: Tasks

Status: **proposed (spec only, not started).** Created 2026-05-16 as
the split-out of v2.63's deferred OTEL path (user decision). Awaiting
alignment on proposal before implementation. **Phase 0 below is a hard
gate — no implementation task may start until it passes (lesson from
v2.63: never build a reader against an assumed Gemini schema).**

- [ ] **Phase 0 (BLOCKING):** enable Gemini telemetry to a file,
  capture a real outfile, record the verified schema in design.md
  (framing, event names, `duration_ms` location, session-id field +
  level). Decide gate: proceed / rewrite-to-real-schema / **defer
  v2.67** if no `outfile` support or no usable session join key
- [ ] `AiSession`: add `api_seconds`/`tool_seconds` (independent
  optionals); `agent_active_seconds` left unchanged; module-level
  `api_plus_tool_seconds()` display helper
- [ ] Serializer emits the two tokens when set; parser reads them;
  helper never serialized; round-trip + forward-compat
- [ ] `collectors/gemini_otel.py`: bounded OTLP-outfile reader,
  sum `duration_ms` per `session.id`, fail-closed to `(None, None)`
- [ ] `gemini_cli.handle_agent_stop`: resolve telemetry outfile from
  Gemini settings, enrich `api_seconds`/`tool_seconds`, best-effort
- [ ] `halyard install-gemini-telemetry` (no-clobber / diff-approve /
  byte-stable no-op, v2.45/v2.51 pattern)
- [ ] `halyard doctor` nudge: hook on + telemetry off ⇒ `warn`
- [ ] Surface: session-detail "active time" line;
  `mcp_server.sessions` includes the fields
- [ ] Tests: `tests/test_v267_gemini_otel.py` (9 cases incl. privacy,
  bounded-read, no-op, doctor nudge)
- [ ] `docs/PRD-ai-work-ledger.md` "What Is Captured" + opt-in
  telemetry note
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
