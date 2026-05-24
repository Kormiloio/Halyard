# Tasks: v5.0 Duplicate-Effort Detection

## Phase 1: Logic & Core
- [x] 1.1 Implement `find_collisions` logic in `src/halyard/collisions.py`.
- [x] 1.2 Add `get_recent_branch_activity` query to `db.py`.
- [x] 1.3 Add unit tests for various overlap scenarios (partial, full, sequential).

## Phase 2: Hub & Eventing
- [x] 2.1 Update `HubServer` to check for collisions on ingestion.
- [x] 2.2 Emit `collision_detected` event via the Hub SSE stream.
- [x] 2.3 Update CLI `start` command to ping the Hub for collision checks.

## Phase 3: UI Surfacing
- [x] 3.1 Surface per-branch collision counts on the dashboard — a dedicated
      `data-panel="collisions"` panel keyed by `project · branch` (rather than a
      column inside the existing Projects/attribution table).
- [x] 3.2 Add a basic collision visualization to the project detail page.
- [x] 3.3 Update `halyard status` to report active collisions.

## Phase 4: Validation
- [x] 4.1 Integration test: concurrent emissions on the same branch.
- [x] 4.2 Verify CLI warning fires correctly on branch reuse.

## Notes
- Fixed the ingest→cache race that left collision checks blind: `HubServer._trigger_cache_sync`
  called `sync_all()` (global registry/hub/CWD discovery) and ignored the dir it just wrote to.
  Added `db.sync_source(project_dir)` to sync the exact written dir; `_trigger_cache_sync` now
  uses it. Both v5 integration tests pass.
- Phase 3 UI and CLI warning (4.2) are now complete and test-covered:
  - 3.1/3.2: `reports.detect_collisions` aggregates overlaps per (remote, branch); the dashboard
    renders a dedicated `data-panel="collisions"` panel (`dashboard._collisions_panel`) with a
    per-branch count and a magnitude bar, and it refreshes via the realtime SSE fragment list.
    The per-active-timer alert (`dashboard._timer_metric` + `reports._detect_timer_collision`)
    remains as the focused in-context warning. Covered by
    `test_v43_realtime_dashboard.test_dashboard_renders_collisions_panel` and
    `test_v5_collisions.test_detect_collisions_*`.
  - 3.3/4.2: `cli_session._maybe_warn_collision` (used by both `start` and `status`, routed
    through `hub_client.check_collisions`) is covered by
    `test_v5_collision_integration.test_cli_collision_warning_*`.
- Bug fix: `dashboard._timer_metric` built the collision-probe `AiSession` without the required
  `cost_usd` field, raising `TypeError` and 500-ing the dashboard whenever an active timer had a
  branch + remote. Added `cost_usd=0.0` (matching the Hub's `/v1/collisions` probe). This is the
  Phase 3 collision panel rendered inside the realtime dashboard.
