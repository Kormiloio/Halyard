# v2.48 — Dashboard Data Correctness: Design

## 1. Aggregate-by-default dashboard

### Session-list injection (the enabling refactor)

`build_ai_report` gains an optional keyword `sessions: list[AiSession]
| None = None`. When provided, it skips `parse_sessions(project_dir)`
and computes the report from the given list (everything downstream
already operates on the session list). Behavior is identical when
`sessions is None` (parse the dir, as today) — purely additive.

### Source resolution

New `reports.aggregate_session_dirs() -> list[Path]`:
- start from `registry.read_registry()` (already existence- and
  `halyard.toml`-filtered),
- add `hub.find_hub()` if present,
- keep only dirs containing `ai-sessions.log`,
- de-dup by resolved path, stable order.

New `reports.build_aggregate_dashboard_state() -> DashboardState`:
- `dirs = aggregate_session_dirs()`,
- `sessions = _dedup(concat(parse_sessions(d) for d in dirs))`,
  deduped by the existing content-addressed session id (fall back to
  `(start,end,tool,model,input,output)` tuple if id absent) so a
  session that appears in both a project log and the hub counts once,
- `report = build_ai_report(primary, all_time=False, sessions=sessions)`,
- `primary` = current project (`find_project_dir()`) if inside one,
  else hub, else first source — used only for the inherently
  per-project panels (timeclock, plans, budget, file-health) and the
  header label,
- header shows `All Projects · N` when aggregating.

`render_dashboard(project_dir: Path | None = None)` and the HTTP
handler: `None` → `build_aggregate_dashboard_state()`; an explicit
`Path` → existing single-project `build_dashboard_state` (unchanged).
`cli_report.dashboard`: when `--project-dir` is omitted, pass `None`
(aggregate) instead of `find_hub() or find_project_dir()`.

Per-project panels under aggregate mode are scoped to `primary` and
labelled so they're not misread as global; the session-derived panels
(Recent, Usage, Outcomes, Models, Tools, Wake, Captain's, Voyage,
Leverage, cost totals) reflect the union — these are the ones the user
saw as wrong.

## 2. Implausible-session guard

Shared `collectors._MAX_SESSION_SECONDS = 12 * 3600`. In
`session_has_evidence`'s callers (gemini/cursor/claude stop handlers),
before append, also drop when
`(session.end - session.start).total_seconds() > _MAX_SESSION_SECONDS`.
Gemini already has a 12h stale-state guard; this generalises it to all
three and catches the frozen-`2026-05-07`-start synthetic Cursor rows
(>8 days). Helper: `collectors.session_is_implausible(session)`; the
guard becomes `if not session_has_evidence(...) or
session_is_implausible(session): return 0` (state still reset).

## 3. Registry test-isolation

- `conftest.py`: autouse fixture pointing `registry.REGISTRY_PATH`
  (and any module-cached refs) at a tmp file for every test, so no
  test can touch the real registry. Apply the same to `cli_setup` /
  `orchestration` init paths if they bypass `registry`.
- Guard in `register_project`: skip paths under the system temp dir
  (`tempfile.gettempdir()`) — a real project is never there; this also
  hardens production against accidental temp registration.
- Operational: prune the existing temp lines from the user's real
  `~/.halyard/projects` (backup kept).

## 4. Log re-clean (operational)

Same safe method already used: backup → removed-file → predicate
(`session_has_evidence` + `not implausible`) atomic rewrite, applied to
the hub log (344 stubs) and re-verified on the project log.

## Tests

- `build_ai_report(sessions=…)` ignores the dir and uses the list;
  `sessions=None` unchanged (regression).
- `aggregate_session_dirs` = registry∩existing ∪ hub, deduped, skips
  dirs without a log.
- aggregate state dedups a session present in two source logs.
- `session_is_implausible`: >12h True, normal False; collector drops an
  implausible hook session (gemini+cursor+claude).
- `register_project` refuses a tempdir path; autouse fixture keeps the
  real registry untouched across the suite.
- dashboard renders in aggregate mode (header "All Projects", union
  counts) and still renders single-project with `--project-dir`.

Browser-verify the aggregate dashboard shows real cross-project work.
Full `pytest`+`ruff`+`ruff format --check`+`mypy` before commit.
