# v2.50 — Halyard MCP Server: Tasks

- [x] pyproject: `[mcp]` optional dep (`mcp>=1.2`) + add to `all`
- [x] `mcp_server.py`: SDK-free `_*` data helpers + `build_server()`
  (lazy FastMCP import) — work_summary/sessions/spend_in_range/
  project_breakdown/cost_by_model/outcomes_status, read-only
- [x] `cli_mcp.py`: `halyard mcp` (stdio) + actionable error if SDK
  missing; `register(app)` wired in `cli.py`
- [x] repo-root `.mcp.json` + README/docs snippet
- [x] Tests: `tests/test_v250_mcp_server.py` (helpers + missing-SDK
  exit), SDK-free

## Gate
- [x] `pytest` green (1068 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean (optional import guarded via mypy overrides)
- [x] `halyard mcp` smoke (with SDK installed, lists 6 tools)
- [x] roadmap entry + status in `openspec/project.md`
