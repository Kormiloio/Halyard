# Tasks: v4.3 Real-Time Dashboard

## Phase 1: Hub Event Stream
- [x] 1.1 Implement `EventEmitter` in `hub_server.py`.
- [x] 1.2 Add `GET /v1/events` SSE endpoint.
- [x] 1.3 Add keep-alive logic for the stream.

## Phase 2: Reactive UI
- [x] 2.1 Add `events.js` to dashboard assets (or inline in template).
- [x] 2.2 Implement DOM-patching logic for the ledger table.
- [x] 2.3 Verify that a `curl` ingestion triggers a UI update in the browser.

## Phase 3: Timer Reactivity
- [x] 3.1 Emit `timer_updated` events from the Hub.
- [x] 3.2 Update the dashboard's "Active Project" card in real-time.

## Phase 4: Post-review fixes
- [x] 4.1 Fix SSE event-queue locking: `_handle_sse` drained each listener deque under
      `HubServer._lock` while `EventEmitter.emit` appended under `EventEmitter._lock` — two
      different locks guarding the same deque. Added `EventEmitter.drain()` so append and
      drain share one lock; the SSE handler now calls it instead of draining under the
      unrelated hub lock.
