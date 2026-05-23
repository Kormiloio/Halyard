# v2.44 — TUI Health Visibility: Tasks

- [x] `HalyardApp._health_checks()` helper (build_health_checks on the
  store's project dir)
- [x] `_status_text()` appends `[⚠ N — press h]` chip when failing only
- [x] `tui/widgets/health_modal.py` — `HealthModal` (escaped rows +
  `halyard doctor` footer, healthy fallback)
- [x] `("h", "open_health_modal", "health")` binding + action
- [x] Tests: `tests/test_tui_health.py`

## Gate

- [x] `pytest` green (1029 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 23)
- [x] PRD reviewed — additive TUI parity; no scope/priority change; behavior in `specs/tui-health.md`
