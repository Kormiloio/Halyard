# v2.59 — Collector Schema-Drift Canary: Tasks

Status: **complete (1150 tests passing)**.

- [x] `doctor.py`: `_DRIFT_WINDOW`, `_model_unreal`,
  `_collector_drift_checks(project_dir, hub_dir)` (per-tool, sustained
  regression vs own healthy baseline → `warning` + fix)
- [x] Wire into `build_doctor_report()` after `_unwired_tool_checks`
- [x] Tests: `tests/test_v259_collector_drift.py` (8 cases incl.
  exit-code contract + JSON surface)
- [x] Roadmap entry in `openspec/project.md` (item 36)
- [x] Health-surface lineage note in `current-direction.md`

## Gate
- [x] `pytest` green (1150 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
