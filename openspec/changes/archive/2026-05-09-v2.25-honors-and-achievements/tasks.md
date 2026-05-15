# Tasks: v2.25 Honors and Achievements

- [x] Create `src/halyard/achievements.py`
  - [x] `RankDef`, `Medal`, `ServiceRecord` dataclasses
  - [x] `RANKS` catalog (8 levels: Civilian through Commodore)
  - [x] `MEDALS` catalog (8 medals)
  - [x] `_extract_watches(project_dir)` — parse timeclock into Watch objects
  - [x] `_watch_streak(watches, *, as_of)` — consecutive-day streak
  - [x] `_clean_watch_days(watches, sessions)` — set of days where all sessions
        are attributed + have tokens
  - [x] `_clean_watch_streak(clean_days, *, as_of)` — clean-watch streak
  - [x] `_evaluate_rank(attributed_count)` — (current, next, sessions_toward_next)
  - [x] `_evaluate_medals(project_dir, sessions, watches, clean_days)` — list of
        earned medals
  - [x] `_compute_proof_score(sessions)` — 0-100 int
  - [x] `build_service_record(project_dir, sessions, *, as_of)` — public API

- [x] Add `halyard honors` CLI command to `src/halyard/cli.py`
  - [x] Load project dir (find_project_dir or find_hub)
  - [x] Parse sessions, build service record
  - [x] Rich panel: rank icon + name + flavor, progress bar, stripes, proof score
  - [x] Medal list with name + description + detail text
  - [x] Rank ladder showing all 8 ranks, current highlighted

- [x] Add Captain's Quarters panel to `src/halyard/dashboard.py`
  - [x] `_captains_quarters_panel(project_dir, sessions)` function
  - [x] Rank row: icon, name, flavor text, progress bar
  - [x] Stripes row: bar + gold stripe indicator
  - [x] Medal list with title= attribute for hover detail
  - [x] Rank ladder sidebar
  - [x] Wire into `_render_state()` grid after `_voyage_panel()`
  - [x] Add `cq-*` CSS classes to `_CSS`

- [x] Create `tests/test_achievements.py`
  - [x] Rank catalog sanity (sorted by level, non-decreasing sessions_required,
        unique medal keys)
  - [x] `_evaluate_rank`: civilian at 0, deckhand at 1, commodore at 1000,
        exact boundary, just-below boundary
  - [x] `_watch_streak`: no watches, single day, consecutive days, gap breaks
        streak, yesterday-only returns 0
  - [x] `_clean_watch_streak`: empty, counts consecutive
  - [x] `_extract_watches`: empty timeclock, parses entries correctly
  - [x] `_evaluate_medals`: eight bells, full sail, clean manifest, lighthouse,
        signal master, harbor master, rescue
  - [x] `build_service_record`: civilian no data, deckhand after 1 session,
        watch streak, proof score 100%, proof score mixed, gold stripe, next_rank
        None at Commodore

- [x] ruff check + ruff format — all clean
- [x] mypy `src/halyard/achievements.py src/halyard/dashboard.py` — no errors
- [x] Full test suite: 762 passed
