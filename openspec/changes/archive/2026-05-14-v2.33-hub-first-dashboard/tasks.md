# Tasks: v2.33 — Hub-First Dashboard & Voyage Auto-Detection

## Hub-first scope
- [x] `cli_report.py` dashboard command resolves hub before project dir
- [x] `DashboardState` gains `all_sessions: list[AiSession]` field
- [x] `build_dashboard_state()` populates `all_sessions` via `parse_sessions()`
- [x] `_render_state()` uses `state.all_sessions` for usage analytics (no double-read)

## Voyage auto-detection
- [x] `_infer_voyage_stage(sessions)` added to `dashboard.py`
- [x] Stages: At anchor / Anchors Aweigh / Making Headway / Rounding the Mark / Flying Colors
- [x] `_voyage_panel` else-branch uses inferred stage for title and eyebrow
- [x] Eyebrow shows "auto" when stage is inferred
- [x] Sessions column adds "N all time" sub-label

## Timeclock health bug fix
- [x] `_timeclock_check()` returns "neutral" (not "error") when `time.timeclock` absent
- [x] Spurious red "Error" pill eliminated for projects without human-time tracking

## Quality gates
- [x] 952 tests passing
- [x] ruff check clean
- [x] mypy clean (71 source files)

## Docs
- [x] `openspec/project.md` updated
- [x] `docs/current-direction.md` updated
