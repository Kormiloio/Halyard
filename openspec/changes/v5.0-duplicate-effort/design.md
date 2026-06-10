# Design Doc: v5.0 Duplicate-Effort Detection

## 1. The Collision Engine
A new utility module `halyard.collisions` will handle the overlap logic.
```python
def find_collisions(session: AiSession, history: list[AiSession]) -> list[AiSession]:
    # Logic to find sessions with matching (remote, branch)
    # that overlap in time with [session.start, session.end]
```

## 2. Hub Integration
When the Hub ingests a session:
1. It queries the SQLite cache for the most recent session on that `(remote, branch)`.
2. If the new session's start time is within `N` minutes of the previous session's end (or overlaps), it emits a `collision_detected` event.

## 3. SQLite Schema
No schema changes are strictly required, as we already store `branch` and `remote`. We will add a `collided_with` field to the `sessions` table (optional) or just calculate overlaps at query time for better flexibility.
Update: We'll calculate at query time in the dashboard for now to avoid migration overhead, but we may add an index on `(remote, branch)` for performance.

## 4. Dashboard UI
- Add a "Collisions" panel to the project view. **Built:** a full-width
  `data-panel="collisions"` panel (`dashboard._collisions_panel`) lists each
  (remote, branch) with overlapping effort, the overlap count, the tools involved,
  and how recent the latest overlap is.
- Render overlapping sessions to visualize the conflict. **Built (basic):** instead of
  a full Gantt, each branch row carries a magnitude bar scaled to the branch with the
  most overlaps — consistent with the dashboard's existing bar idiom. A richer
  per-session timeline is deferred.
- The panel is registered in the realtime SSE fragment map, so it patches in place on
  `session_ingested` / `collision_detected` without a full reload.

## 5. Review follow-up (performance & consistency)
- Branch/remote resolution in `read_active_timer` shells out to git twice; it is now
  gated behind a `resolve_git=False` default so hot/polled callers (status, reports,
  TUI watch pane) stay cheap. Only the dashboard builders pass `resolve_git=True`.
- The dashboard collision lookup is computed **once** per state build via
  `_detect_timer_collision` and carried on `DashboardState.timer_collision`
  (`TimerCollision`), instead of running a DB query inside `_timer_metric` on every
  render / reactive refetch.
- The CLI collision warning (`_maybe_warn_collision`) and the hub-first append
  (`ai_log._try_append_to_hub`) route through `hub_client` (`check_collisions`,
  `ingest_line`) so `HALYARD_DISABLE_HUB` and the configured host/port are honored
  uniformly; the dashboard SSE listener URL is derived from `hub_client.hub_url()`.
