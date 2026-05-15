# v2.45 — Cursor/Gemini Hook Install De-dup: Tasks

- [x] `_is_halyard_hook_cmd(cmd)` helper (arg0 basename = halyard)
- [x] `_do_install_hook_gemini`: drop all halyard blocks per event,
  re-add one for current exe; preserve foreign blocks
- [x] `_do_install_hook_cursor`: same, flatter; preserve foreign entries
- [x] Idempotent messaging (no-op leaves file byte-unchanged)
- [x] Tests: `tests/test_hook_dedup.py`

## Gate

- [x] `pytest` green (1034 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 24)
