# Design Doc: v4.3 Real-Time Dashboard

## 1. Server-Sent Events (SSE)
We will use SSE instead of WebSockets to keep the Hub lightweight and standard-compliant.
- Endpoint: `http://localhost:4318/v1/events`.
- Format: `data: {"type": "session_ingested", "data": {...}}\n\n`.
- Keep-alive comments are sent periodically while the connection is open.

## 2. EventEmitter
The `HubServer` will implement a simple publisher-subscriber pattern.
- The `_write_to_log` method will trigger an event after a successful append.
- The SSE handler will subscribe to these internal events.

## 3. Dashboard UI
Add a small JS script to the Bridge template:
- It connects to `/v1/events`.
- On `session_ingested`, `timer_started`, `timer_stopped`, or `timer_updated`,
  it fetches the current dashboard HTML and patches matching
  `data-hub-fragment` regions.
- It MUST NOT call `window.location.reload()` for Hub events.
- If EventSource or fetch fails, it closes the stream quietly and leaves the
  static dashboard alone.

Implementation note: The dashboard marks patchable regions with
`data-hub-fragment` and the inline listener replaces matching regions from a
fresh server-rendered dashboard document. Table sorting is re-booted after patch
through `window.HalyardBootTables`.
