# v2.63 — Session Time Decomposition: Tasks

Status: **proposed (spec only, not started)**.

- [ ] `AiSession`: add `api_seconds`/`tool_seconds` (optional) +
  `agent_active_seconds` derived property
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
