# v2.63 — Session Time Decomposition: Tasks

Status: **DEFERRED 2026-05-16 (user decision).** Phase 0 audit found
the change unbuildable as specced: (1) `agent_active_seconds` is
already a stored/serialized field used by work_health + the
record-session CLI — the design's "derive it, never store" is a
breaking change; (2) Gemini exposes NO api/tool timing to any
collector by default — the `/quit` split is terminal-only; on-disk
session JSON has timestamps but no durations; structured api/tool
latency exists only via opt-in OpenTelemetry. Deferred until a tool
exposes the split to a collector. The OTEL path is split out as its
own changeset → **v2.67-gemini-otel-ingestion** (spec only). Codex
`tool_seconds` residue is not worth a standalone schema bump.

- [x] Phase 0: audit data sources + existing schema; conflicts
  recorded in design.md
- [ ] `AiSession`: add `api_seconds`/`tool_seconds` (optional) +
  `agent_active_seconds` derived property — BLOCKED (Conflict 1)
- [ ] Serializer emits the two tokens when set; parser reads them;
  property never serialized
- [ ] Collectors: Gemini (from `/quit` summary), Codex (rollout
  timing if present); Claude/Cursor → `None` (documented limitation)
- [ ] Surface: session-detail "active time" line; `mcp_server.sessions`
  includes the fields
- [ ] Tests: `tests/test_v263_time_decomposition.py` (5 cases)
- [ ] `docs/PRD-ai-work-ledger.md` "What Is Captured" updated
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
