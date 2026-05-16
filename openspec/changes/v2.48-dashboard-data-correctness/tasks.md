# v2.48 — Dashboard Data Correctness: Tasks

## Code
- [x] `build_ai_report(..., sessions=None)` — use list if given, else
  parse dir (additive, regression-safe)
- [x] `reports.aggregate_session_dirs()` + `_dedup_sessions()`
- [x] `reports.build_aggregate_dashboard_state()`
- [x] `render_dashboard(project_dir: Path | None)` + handler + CLI
  default → aggregate when no `--project-dir`
- [x] Header shows `All Projects · N` in aggregate mode
- [x] `collectors.session_is_implausible()`; wire into gemini/cursor/
  claude stop guards (+ `_MAX_SESSION_SECONDS`)
- [x] `registry.register_project` rejects tempdir paths
- [x] `conftest.py` autouse fixture isolates `registry.REGISTRY_PATH`

## Tests
- [x] `tests/test_v248_dashboard_data.py` (report-sessions arg,
  aggregate dirs/dedup, implausible guard ×3 collectors, registry
  tempdir reject, aggregate render)

## Operational (backups, not committed)
- [x] prune temp paths from real `~/.halyard/projects`
- [x] re-clean hub log (predicate + implausible), verify project log

## Gate
- [x] `pytest` green (1059 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] verified aggregate state: 9 real source dirs, 719 sessions, $2116 (programmatic; browser optional)
- [x] roadmap entry + status in `openspec/project.md` (item 27)
