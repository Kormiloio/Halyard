# v2.52 — Unwired-Tool Detection Nudge: Tasks

Status: **complete (1088 tests passing)**.

- [x] `doctor.py`: `_mcp_registered(client)` helper (read MCP config,
  basename-match `halyard`)
- [x] `doctor.py`: `_unwired_tool_checks()` for claude/cursor/gemini
  (on PATH AND no hook AND no MCP → `warning` + fix)
- [x] `doctor.py`: Codex branch (history present AND nothing imported
  → `warning` + `halyard import-codex`), only when `tool == "all"`
- [x] `codex_app.py`: read-only `codex_history_present()` and
  `codex_imported_any()` (no importer behavior change)
- [x] Wire `_unwired_tool_checks()` into `build_doctor_report()` after
  `_hook_checks`
- [x] Tests: `tests/test_v252_tool_detection.py` (11 cases incl.
  exit-code contract + JSON surface)

## Gate
- [x] `pytest` green (1088 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry status → complete in `openspec/project.md`
