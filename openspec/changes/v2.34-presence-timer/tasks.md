# Tasks: v2.34 — Presence-Aware Human Timer

## Data model
- [x] `HumanTimeReport` gains `presence_minutes: int = 0` and `presence_label: str`
- [x] `_compute_presence_today(sessions, now)` merges session windows with 30-min gap
- [x] `build_dashboard_state()` computes presence from `all_sessions` and rebuilds `HumanTimeReport`
- [x] Nothing written to `time.timeclock`; presence is computed on read

## Dashboard display
- [x] Human Time metric card shows `presence_minutes` when `today_minutes == 0`
- [x] Sub-label shows "today · auto-detected" for presence time vs "today" for manual
- [x] Manual timer minutes always take precedence over presence estimate

## Quality gates
- [x] 952 tests passing
- [x] ruff check clean
- [x] mypy clean (71 source files)

## Docs
- [x] `openspec/project.md` updated
- [x] `docs/current-direction.md` updated
