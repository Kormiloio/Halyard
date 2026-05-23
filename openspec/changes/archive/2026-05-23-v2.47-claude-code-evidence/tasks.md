# v2.47 — Extend Evidence-Free Guard to Claude Code: Tasks

- [x] Import `session_has_evidence` in `collectors/claude_code.py`
- [x] Guard before append/unattributed in `handle_stop_hook`
  (return 0 on no evidence)
- [x] Tests: skip case in test_v1_collectors
  (test_stop_hook_skips_evidence_free_empty_payload); controls via
  existing real-model token tests + test_evidence_free_sessions
  predicate coverage (no duplicate scaffolding file)

## Gate

- [x] `pytest` green (1053 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 26)
