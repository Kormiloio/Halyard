# v2.46 — Suppress Evidence-Free Collector Sessions: Tasks

- [x] `_session_has_evidence(session, *, history)` predicate (shared
  helper in `collectors/__init__`)
- [x] Gemini `handle_agent_stop`: skip append + reset state when no
  evidence (history flag included)
- [x] Cursor `handle_stop_hook`: skip append when no evidence
- [x] Tests: `tests/test_evidence_free_sessions.py` (skip + control +
  signal-present, both collectors)

## Gate

- [x] `pytest` green (1053 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 25)
