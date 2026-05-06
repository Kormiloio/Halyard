# Tasks

Implementation checklist for v1 — AI Intelligence Layer.

## 1. Core schema infrastructure

- [x] 1.1 Define ai-sessions.log format, tool registry, billing models, deduplication
       rules (design.md)
- [ ] 1.2 Implement `AiSession` dataclass and `ai_log.py` — to_log_line, append,
       parse, find_project_dir
- [ ] 1.3 Implement `pricing.py` — model cost table (snapshot 2026-05) and
       `calculate_cost()` with cache token support
- [ ] 1.4 Update `halyard init` to create `ai-sessions.log` with spec header
- [ ] 1.5 Update `halyard init` tests to assert `ai-sessions.log` is created

## 2. Claude Code hook collector

- [ ] 2.1 Implement `halyard cc-session` — called by UserPromptSubmit hook,
       writes session start timestamp to `~/.halyard/cc-session`
- [ ] 2.2 Implement `halyard cc-hook` — called by Stop hook, reads payload from
       stdin, writes `s` record to `ai-sessions.log`
- [ ] 2.3 Implement `halyard install-hook` — adds cc-session and cc-hook entries
       to `.claude/settings.json` in the current project
- [ ] 2.4 Write tests for cc-hook: complete payload, missing usage, missing model,
       not in Halyard project, deduplication-safe output

## 3. Local analytics

- [ ] 3.1 Implement `halyard report` — sessions, cost, tokens summary; breakdown
       by project and by model; current month by default, `--all` for all time
- [ ] 3.2 Write tests for report: empty log, single session, multi-project,
       multi-model, month filtering
