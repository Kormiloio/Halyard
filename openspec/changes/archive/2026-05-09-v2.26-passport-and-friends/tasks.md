# Tasks: v2.26 Passport and Friends of the Sea

## Passport

- [x] Add `PassportStamp` frozen dataclass to `achievements.py`
- [x] Add `PASSPORT_STAMPS` catalog (claude-code, cursor, gemini-cli, codex, manual)
- [x] Add `_evaluate_passport(sessions)` function
- [x] Add `passport: list[PassportStamp]` field to `ServiceRecord`
- [x] Wire `_evaluate_passport` into `build_service_record()`
- [x] Update `halyard honors` CLI to show Passport section
- [x] Update Captain's Quarters dashboard panel to show passport stamps

## Friends of the Sea — data layer

- [x] Create `src/halyard/voyages.py`
  - [x] `VoyageEntry` dataclass (slug, target_sessions, inactivity_days, stage,
        started_at, completed_at, creature, creature_trait)
  - [x] `read_voyages(project_dir)` — parse voyages.toml
  - [x] `write_voyages(project_dir, entries)` — atomic write (tmp → rename)
  - [x] `voyage_for_slug(entries, slug)` — return entry or default
  - [x] `compute_stage(session_count, target)` — return stage string
  - [x] `assign_creature(slug, sessions, all_completed_counts, coral_reef_flag)`
  - [x] `check_auto_complete(project_dir, sessions_by_project)` — detect and
        write newly-completed projects
  - [x] `build_voyage_summaries(project_dir, sessions_by_project)` — build list for display

## Friends of the Sea — CLI

- [x] Add `voyage_app = typer.Typer(...)` group to `cli.py`
- [x] `halyard voyage` — list all project stages
- [x] `halyard voyage complete <project>` — manual completion
- [x] `halyard voyage set <project>` — edit target/inactivity

## Friends of the Sea — dashboard

- [x] Add `_friends_panel(project_dir, sessions)` to `dashboard.py`
- [x] Wire into `_render_state()` grid after Captain's Quarters
- [x] Add CSS for creature cards (`.friends-grid`, `.friend-card`, etc.)

## Tests

- [x] `tests/test_voyages.py`
  - [x] `read_voyages` — missing file returns defaults
  - [x] `write_voyages` — round-trips correctly, no stale .tmp
  - [x] `compute_stage` — all 5 stage boundaries
  - [x] `assign_creature` — whale, sea turtle, dolphin, octopus, shark, coral
        reef, seal (fallback); noted clownfish is shadowed by dolphin rule
  - [x] `check_auto_complete` — inactivity trigger, target trigger
  - [x] `voyage_for_slug` — found and not-found cases
  - [x] `VoyageSummary.progress_pct` — computed in __post_init__
  - [x] `build_voyage_summaries` — includes all slugs, preserves moored stage
- [x] `tests/test_achievements.py` — passport stamp tests
  - [x] Single tool → one stamp
  - [x] Multiple sessions same tool → one stamp (no duplicates)
  - [x] Unknown tool → generic stamp with `🔧` icon
  - [x] No sessions → empty passport
  - [x] Multiple tools → one stamp each
  - [x] `ServiceRecord.passport` populated by `build_service_record`

## CI

- [x] ruff check + ruff format — clean
- [x] mypy src/halyard/voyages.py src/halyard/achievements.py — no errors
- [x] Full test suite green (799 tests)

## Docs

- [x] Update `project.md` active focus with v2.26 entry
- [x] Tick tasks.md on completion
