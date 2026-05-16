# v2.49 — Require a Recorded Session Start: Tasks

- [x] cursor `handle_stop_hook`: early `return 0` if no
  `_CURSOR_SESSION_FILE`
- [x] gemini `handle_agent_stop`: `return 0` if `_read_state()` is None
- [x] Tests: `tests/test_v249_require_session_start.py` (no-state skip
  + with-state control, both collectors)
- [x] Existing collector tests still green (seed state where needed)

## Gate
- [x] `pytest` green (1062 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 28)

## Operational
- [ ] re-clean hub of the new synthetic batch (backup)
- [ ] advise user on the claude-mem worker-service daemon
