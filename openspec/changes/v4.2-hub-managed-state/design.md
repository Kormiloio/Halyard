# Design Doc: v4.2 Hub-Managed State

## 1. Internal Store
The `HubServer` will own a `ActiveState` object:
```python
@dataclass
class ActiveState:
    project: str | None = None
    started_at: datetime | None = None
    timeclock: Path | None = None
    auto_project: str | None = None
    auto_started_at: datetime | None = None
    auto_timeclock: Path | None = None
    last_presence: datetime | None = None
```

## 2. API Endpoints
- `GET /v1/state`: Returns the `ActiveState` as JSON.
- `POST /v1/state/timer`: With `action="start"|"stop"`.
- `POST /v1/state/presence`: With `action="activity"|"update"|"close_stale"|"close_now"`.
- Token authentication will be required for mutations.

## 3. Persistence
To ensure stability across restarts, the Hub will mirror manual timer state to
`~/.halyard/active` using the existing key/value format. On startup, the Hub
initializes itself from this file. Auto-timer presence remains compatible with
the existing `~/.halyard/auto-timer` fallback path.

## 4. Library Delegation
`read_active_project()`, `read_active_timer()`, `start_timer()`, `stop_timer()`,
and `auto_timer.py` attempt a fast loopback Hub call first. If the Hub is down
or returns an invalid response, they fall back to the existing file-based logic.

Implementation note: `hub_client.py` centralizes the loopback calls and honors
`HALYARD_HUB_HOST`, `HALYARD_HUB_PORT`, and `HALYARD_DISABLE_HUB` for tests and
explicit fallback. The Hub endpoint calls direct local timer paths to avoid
delegation recursion.

**Review follow-up (port consistency):** the dashboard-embedded `HubServer` and
`halyard hub start` now bind `hub_client.hub_port()` so client and server agree on
`HALYARD_HUB_PORT` (previously the server hard-bound 4318 while clients honored the
env var, silently breaking all Hub calls when it was set). Caveat: 4318 is the
OTLP/HTTP standard port — if `HALYARD_HUB_PORT` moves the Hub off 4318, external OTLP
emitters (e.g. VS Code Copilot) must be pointed at the new port or their telemetry is
no longer received.

**Review follow-up (write authority — no split-brain):** the loopback helpers now
distinguish *Hub unreachable* (transport failure ⇒ `None` ⇒ fall back to a local
write) from *Hub reachable but rejected the write* (`{"_hub_error": status}`). On the
latter the Hub is the live authority, so callers must NOT write divergent local state
behind its back: `start_timer` raises `orchestration.HubStateError` (surfaced by the
CLI / suppressed by the dashboard), while `stop_timer` and the auto-timer presence
calls degrade to a no-op. Reads (`read_state`) still fall back to disk on any error
since a read cannot create divergence.

**Post-review correction:** `read_active_timer()` defaults to `prefer_hub=False`
(disk-first), not hub-first. Because the Hub mirrors timer state to
`~/.halyard/active` on every start/stop (§3), the disk file is already an accurate
source of truth, and a hub-first default silently rerouted ~9 existing no-arg
callers through in-memory state that could drift from disk. Callers that genuinely
need the live in-memory view pass `prefer_hub=True` explicitly. `start_timer`/
`stop_timer` still delegate to the Hub for the *write* path.
