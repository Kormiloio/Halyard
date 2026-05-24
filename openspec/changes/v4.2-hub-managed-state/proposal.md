# OpenSpec Proposal: v4.2 Hub-Managed Active State

## 1. Why
State is currently fragmented. The active project is tracked in `~/.halyard/active`, and the auto-timer has its own logic. This leads to latency (hooks must read the disk to know which project to attribute a session to) and potential desync. By moving "Active State" into the Hub's memory, we create a single, fast, source of truth.

## 2. What
- **Hub State Storage:** The Hub maintains the `active_project`, `timer_started_at`, and `presence_window` in memory.
- **State API:** New endpoints:
  - `GET /v1/state`: Returns the current active state.
  - `POST /v1/state/timer`: Starts or stops a manual timer with `action=start|stop`.
  - `POST /v1/state/presence`: Records or closes auto-timer presence windows.
- **Zero-Disk Hooks:** CLI and IDE collectors query the Hub API instead of checking `~/.halyard/active`.

## 3. Implementation High-Level
- Extend the Hub's `ActiveState` store.
- Persist state to `~/.halyard/active` only on Hub shutdown or state change (as a backup).
- Update `halyard.ai_log.read_active_project` to prefer the Hub.
