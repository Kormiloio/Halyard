# v3.6 — Windsurf Collector: Design

## Where

- **New module:** `src/halyard/collectors/windsurf.py` — handles hook entry
  points and payload parsing.
- **CLI Commands:**
  - `halyard windsurf-session-start`: Called by `pre_user_prompt` hook.
  - `halyard windsurf-session-stop`: Called by `post_cascade_response` hook.
  - `halyard install-windsurf-hook`: Manages `~/.codeium/windsurf/hooks.json`.
- **State Dir:** `~/.halyard/ws-sessions/` — stores `<trajectory_id>.json`
  files with `start_dt`, `model`, `user_count`, `assistant_count`, and
  `last_activity`.

## Hook Integration

Windsurf's `hooks.json` uses the following structure:

```json
{
  "hooks": {
    "pre_user_prompt": [
      {
        "command": "halyard windsurf-session-start",
        "show_output": false
      }
    ],
    "post_cascade_response": [
      {
        "command": "halyard windsurf-session-stop",
        "show_output": false
      }
    ]
  }
}
```

The `install-windsurf-hook` command will:
1. Create `~/.codeium/windsurf/` if it doesn't exist.
2. Load existing `hooks.json`.
3. Idempotently add the Halyard commands to the relevant lists.
4. Preserve existing non-Halyard hooks.

## Payload Parsing (Confirmed)

The spike (2026-05-23) confirmed that Windsurf passes a JSON payload
via stdin.

Key fields:
- `trajectory_id`: Stable UUID string.
- `model_name`: Display name (e.g. "SWE-1.6 Slow").
- `timestamp`: ISO-8601 with offset.

**Unobserved:** token counts (`input`/`output`) are not present in the
current hook payloads. Sessions will be written with `tokens_available=false`.

## Session Lifecycle

### Turn Capture
- `halyard windsurf-session-start` (on `pre_user_prompt`):
  - Increments `user_message_count` for the `trajectory_id`.
  - Records `start_dt` on first turn.
  - Updates `last_activity`.
- `halyard windsurf-session-stop` (on `post_cascade_response`):
  - Increments `assistant_message_count` for the `trajectory_id`.
  - Updates `last_activity`.

### State Storage
Per-trajectory state is stored in `~/.halyard/ws-sessions/<trajectory_id>.json`.
This avoids lock contention between concurrent Cascades and ensures
clean attribution.

### Finalization (TTL)
Since Windsurf has no "Session End" hook, Halyard will auto-finalize
sessions that have seen no activity for > 30 minutes. Finalization
writes the record to `ai-sessions.log` and deletes the trajectory
state file. Triggered by subsequent hooks or `halyard outcome sync`.

## Verification

### Phase-0 Spike
- Completed 2026-05-23. Confirmed JSON payloads and `trajectory_id` utility.

### Automated Tests
- Unit tests in `tests/test_v36_windsurf_collector.py`.
- Mocked `hooks.json` read/write tests.
- Mocked payload parsing tests.
