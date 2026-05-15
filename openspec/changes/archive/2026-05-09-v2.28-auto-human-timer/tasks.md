# v2.28 Auto Human Timer — Tasks

## Implementation

- [x] 1. Create `src/halyard/auto_timer.py`
  - [x] `auto_timer_activity(cwd, project_dir)` — open auto-timer if needed, update last-activity
  - [x] `auto_timer_close_if_stale(inactivity_minutes=30)` — close open auto-timer if stale
  - [x] `auto_timer_close_now()` — close open auto-timer immediately (called by `halyard timer stop`)
  - [x] State read/write helpers for `~/.halyard/auto-timer`
  - [x] Timeclock write helpers (append `i`/`o` with `;auto` comment)

- [x] 2. Wire into `src/halyard/collectors/claude_code.py`
  - [x] `record_session_start()` — call `auto_timer_close_if_stale()` then `auto_timer_activity()`
  - [x] `handle_stop_hook()` — call `auto_timer_activity()` to update last-activity timestamp

- [x] 3. Wire into `halyard timer stop` in `src/halyard/cli.py`
  - [x] Call `auto_timer_close_now()` when manual stop is run

- [x] 4. Write `tests/test_auto_timer.py`
  - [x] Auto-timer opens on first session start
  - [x] Auto-timer stays open across multiple sessions within 30 min
  - [x] Auto-timer closes and reopens after 30+ min gap
  - [x] Manual timer suppresses auto-timer
  - [x] `halyard timer stop` closes auto-timer
  - [x] Attribution: git inference → unattributed fallback
  - [x] Timeclock entry has `;auto` comment

- [x] 5. Update docs
  - [x] `docs/PRD-halyard.md` — update Human time section
  - [x] `docs/current-direction.md` — mark v2.28 shipped
  - [x] `openspec/project.md` — add v2.28 entry
