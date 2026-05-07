# Tasks

Implementation checklist for v1 — AI Intelligence Layer.

## 1. Core schema infrastructure

- [x] 1.1 Define ai-sessions.log format, tool registry, billing models, deduplication
       rules (design.md)
- [x] 1.2 Implement `AiSession` dataclass and `ai_log.py` — to_log_line, append,
       parse, find_project_dir; also `assign_unattributed_sessions()`
- [x] 1.3 Implement `pricing.py` — model cost table (snapshot 2026-05) and
       `calculate_cost()` with cache token support
- [x] 1.4 Update `halyard init` to create `ai-sessions.log` with spec header
- [x] 1.5 Update `halyard init` tests to assert `ai-sessions.log` is created

## 2. Claude Code hook collector

- [x] 2.1 Implement `halyard cc-session` — called by UserPromptSubmit hook,
       writes session start timestamp to `~/.halyard/cc-session`
- [x] 2.2 Implement `halyard cc-hook` — called by Stop hook, reads payload from
       stdin, writes `s` record to `ai-sessions.log`
- [x] 2.3 Implement `halyard install-hook` — adds cc-session and cc-hook entries
       to `.claude/settings.json` in the current project
- [x] 2.4 Write tests for cc-hook: complete payload, missing usage, missing model,
       not in Halyard project, deduplication-safe output

## 3. Local analytics

- [x] 3.1 Implement `halyard report` — sessions, cost, tokens, human time summary;
       breakdown by project, model, and human time by project; current month by
       default, `--all` for all time
- [x] 3.2 Write tests for report: empty log, single session, multi-project,
       multi-model, month filtering

## 4. Manual capture and demo tools

- [x] 4.1 Implement `halyard record-session` — manual AI session capture with
       tool, model, tokens, cost, duration, and note options
- [x] 4.2 Implement `halyard sample-session` — appends realistic claude-sonnet-4-6
       demo session for dashboard walkthroughs
- [x] 4.3 Implement `halyard assign-unattributed` — assigns sessions missing
       `project=` to a target project slug (active timer or --project flag)

## 5. Local Glass Cockpit dashboard

- [x] 5.1 Implement `halyard dashboard` — starts ThreadingHTTPServer with
       auto-refreshing dark-theme HTML dashboard
- [x] 5.2 Dashboard panels: AI sessions stream, cost metrics, health checks,
       human timeclock, project/model/tool attribution, unattributed sessions
- [x] 5.3 Shared data layer: `reports.py` — `DashboardState`, `build_dashboard_state`,
       `build_health_checks`, `HumanTimeReport`, `build_human_time_report`,
       `parse_timeclock`, `format_minutes`, `ActiveTimer.elapsed_label`
- [x] 5.4 Write tests for dashboard rendering
