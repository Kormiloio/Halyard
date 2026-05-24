# Behavior Spec: Hub-Managed State (v4.2)

## R1: Hub as Single Source of Truth
The Hub MUST manage the active timer state.

**Scenario: Querying active state**
- GIVEN the Hub is running and a timer is active for project `halyard`
- WHEN a tool calls `GET /v1/state`
- THEN the Hub MUST return `{"project": "halyard", "started_at": "...", "timeclock": "..."}`.

## R2: Remote State Mutation
A tool MUST be able to start/stop the timer via the Hub.

**Scenario: Starting timer via Hub**
- GIVEN the Hub is running
- WHEN the CLI runs `halyard start my-project`
- THEN the CLI MUST send a request to the Hub
- AND the Hub MUST update its internal state
- AND the Hub MUST return `200 OK`.

**Scenario: Mutating state without token**
- GIVEN the Hub is running
- WHEN a tool sends `POST /v1/state/timer` without the dashboard token
- THEN the Hub MUST return `401 Unauthorized`
- AND the Hub MUST NOT update its internal state.

## R3: Fallback Behavior
Halyard MUST remain functional if the Hub is offline.

**Scenario: Hub is down during start**
- GIVEN the Hub is NOT running
- WHEN the CLI runs `halyard start my-project`
- THEN the CLI MUST fallback to writing to `~/.halyard/active` directly.

## R4: Auto-Timer Presence
The Hub MUST own auto-timer presence windows while it is reachable.

**Scenario: Presence activity via Hub**
- GIVEN the Hub is running
- WHEN `auto_timer_activity()` records activity for a project
- THEN the Hub MUST update `last_presence`
- AND the auto-timer MUST still write hledger-compatible `i`/`o` entries.

## Validation
- `tests/test_v42_hub_state.py::test_state_timer_mutation_requires_token`
- `tests/test_v42_hub_state.py::test_hub_start_updates_state_and_mirrors_active_file`
- `tests/test_v42_hub_state.py::test_library_timer_calls_delegate_to_hub_then_stop`
- `tests/test_v42_hub_state.py::test_status_json_reads_active_timer_from_hub`
- `tests/test_v42_hub_state.py::test_auto_timer_presence_is_hub_driven`
- Related regression gate: `tests/test_v41_polyglot.py`,
  `tests/test_v4_hub_server.py`, `tests/test_start_stop.py`, and
  `tests/test_auto_timer.py`.
