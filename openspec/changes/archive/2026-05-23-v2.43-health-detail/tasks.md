# v2.43 — Actionable Health Warnings: Tasks

- [x] Confirmed dashboard `HealthCheck` has no `fix` field (only the
  `doctor` CLI's `DoctorCheck` does) — popup points to `halyard doctor`
  instead of fabricating per-check fixes
- [x] Topbar pill → `<button id="health-pill">` with summarizing `title`
- [x] `_health_popup(state.health)` hidden server-rendered container
- [x] `_health_popup_script()` toggle/close (Esc, outside, button),
  fail-safe; wired into page
- [x] CSS: button reset on `.status`, `#health-popup`, card, rows,
  `.health-fix`, backdrop
- [x] Tests: `tests/test_dashboard_health_detail.py`
- [x] Browser-verify: tooltip, open/close paths, content, no console err

## Gate

- [x] `pytest` green (1023 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 22)
- [x] PRD reviewed — additive dashboard UX, no scope/priority change; behavior authoritative in `specs/health-detail.md`
