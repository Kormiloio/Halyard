# v2.53 — Parse-Time Synthetic-Telemetry Guard: Tasks

Status: **complete (1096 tests passing)**.

- [x] `collectors/__init__.py`: `_SYNTHETIC_FINGERPRINTS` +
  `session_is_synthetic_telemetry(session)`
- [x] `ai_log.parse_sessions`: filter synthetic rows from result
  (local import to avoid cycle), file left untouched
- [x] Write-path defence: `or session_is_synthetic_telemetry(...)` in
  claude_code / cursor / gemini_cli stop guards
- [x] Tests: `tests/test_v253_synthetic_read_guard.py` (8 cases)
- [x] Roadmap entry + status in `openspec/project.md`

## Gate
- [x] `pytest` green (1096 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
