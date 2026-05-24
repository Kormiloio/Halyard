# Design Doc: Halyard Hub (v4.0)

## 1. Technical Strategy
- **Ingestion:** Use `FastAPI` (or lightweight `http.server`) to provide a local OTLP-compatible receiver.
- **Data Flow:** `POST /v1/traces` -> Parse JSON -> `AiSession` -> Append Queue -> `ai_log.append_session`.
- **Service Management:**
  - Create `halyard/service_providers/` directory.
  - Implement a base `ServiceProvider` class with `install()`, `uninstall()`, `status()`, `get_port()`.
  - Refactor `service.py` to use these providers based on `sys.platform`.
  - **Post-review:** `uninstall()` returns `bool` (True when a service was actually
    removed) so the CLI can report "Service is not installed." accurately. Unimplemented
    providers (Windows) raise `NotImplementedError` rather than returning a placeholder
    string. The macOS `_plist` XML-escaping guard moved into `LaunchdProvider`; the
    systemd provider quotes its `ExecStart` arguments to match that safety property.

## 2. State & Persistence
- The Hub maintains an in-memory queue for log appends.
- `cache.db` updates are triggered by the queue processor after a successful log write.
- **Review follow-up:** the per-write cache sync is coalesced per directory — if a
  sync is already running for a dir, the dir is flagged for a single re-run instead of
  spawning another thread, so a burst of writes collapses to at most one extra sync
  (previously one full-log `sync_source` thread was spawned per write).

## 3. Security
- Bind ONLY to `127.0.0.1`.
- Token-based auth (existing `dashboard.token`) for management endpoints.
- OTLP endpoint is open on localhost but metadata-filtered.
- **Post-review:** the open ingest endpoints (`/v1/ingest`, `/v1/traces`) validate a
  loopback `Host` header to block DNS-rebinding / browser CSRF writes into the ledger
  (see v4.1). The request handler sets a 10s read timeout and verifies the full
  Content-Length body so a slow/half-open client cannot exhaust worker threads.
- **Review follow-up:** loopback `Host` validation is now enforced centrally in
  `do_GET`/`do_POST` for *every* endpoint (state, collisions, events, timer, presence),
  not just the two ingest paths, so a rebinding page cannot read the active project /
  timeclock path either. Timer/presence handlers no longer echo internal exception
  strings to the client (generic 500, detail logged via `_log_error`). Added a
  `GET /health` endpoint so `halyard hub status` can probe liveness without relying on
  a 404.
