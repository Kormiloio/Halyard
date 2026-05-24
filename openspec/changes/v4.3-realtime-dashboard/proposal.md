# OpenSpec Proposal: v4.3 Real-Time Dashboard

## 1. Why
The dashboard currently relies on a 10-second `meta-refresh` or manual reloads to show new data. This makes the experience feel slow and "batchy". With the Hub acting as a central daemon, we can push updates to the dashboard the moment a session is ingested.

## 2. What
- **SSE Stream:** The Hub exposes a `/v1/events` endpoint using Server-Sent Events (SSE).
- **Event Dispatcher:** The Hub emits events like `session_ingested`, `timer_started`, and `timer_stopped`.
- **Reactive Dashboard:** The Bridge dashboard (JS) listens for these events and refreshes specific UI components (tables, cards) without a full page reload.

## 3. Implementation High-Level
- Use `http.server` to send SSE chunks.
- Add an `EventEmitter` to the Hub.
- Update `dashboard.py` templates to include a lightweight SSE listener script.
