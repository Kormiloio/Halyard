# v2.39 — Input Injection Hardening: Tasks

- [x] #1 HIGH — sanitize `business_name` + TOML round-trip check
  (`orchestration.py`)
- [x] #2 HIGH — `_safe_transcript_path` validation + streamed read
  (`collectors/claude_code.py`)
- [x] #3 MEDIUM — size-cap Gemini history read (`collectors/gemini_history.py`)
- [x] #7 LOW — guard `float()` in `rate_history_from_git`
  (`config_history.py`)
- [x] Regression tests (`tests/test_v239_input_injection.py`)

## Gate

- [x] `pytest` green (995 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean (69 files)
- [x] roadmap entry + status in `openspec/project.md` (item 18)
- [x] PRD/ARD reviewed — no scope change (input-validation hardening; authoritative behavior in specs/input-validation.md)
