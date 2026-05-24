# Tasks: v4.2 Hub-Managed State

## Phase 1: Hub State Store
- [x] 1.1 Implement `ActiveState` model.
- [x] 1.2 Add `GET /v1/state` endpoint to `HubServer`.
- [x] 1.3 Add `POST /v1/state/timer` endpoint.

## Phase 2: Refactor Library
- [x] 2.1 Update `ai_log.read_active_project` to attempt a Hub call first.
- [x] 2.2 Update `orchestration.start_timer` and `stop_timer` to delegate to the Hub if present.
- [x] 2.3 Verify that `halyard status` shows the correct project from the Hub.

## Phase 3: Auto-Timer Integration
- [x] 3.1 Migrate `auto_timer.py` presence logic to be Hub-driven.
- [x] 3.2 Ensure the Hub automatically finalizes auto-timer windows in the background.

## Phase 4: Post-review fixes
- [x] 4.1 `reports.read_active_timer` default reverted from `prefer_hub=True` to
      `prefer_hub=False` (see design.md). Defaulting to the Hub silently rerouted ~9
      existing no-arg callers through in-memory state; if the Hub's state ever drifts from
      the on-disk timeclock, reads/stops could target the wrong project. Hub access is now
      explicit/opt-in. Safe because `start_timer`/`stop_timer` mirror state to the disk
      `active` file (verified by `test_hub_start_updates_state_and_mirrors_active_file`).
