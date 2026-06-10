# ARD — Halyard Hub Architecture (v4.0)

## 1. Problem Statement
The current "Every Tool is a Writer" model leads to:
1. **I/O Latency:** CLI hooks and IDE extensions block on `flock()` during appends.
2. **Platform Coupling:** `service.py` is hardcoded to macOS `plist` and `launchctl`.
3. **State Desync:** The SQLite cache is updated on every write, increasing the risk of cache corruption during concurrent access.

## 2. Proposed Solution: Daemon-Broker (The Hub)
Transition to a central Hub process that acts as the exclusive manager for `ai-sessions.log` and `cache.db`.

### 2.1 Component Diagram
```
[AI Tools (Claude, Cursor, Copilot)]
      | (OTLP / HTTP)
      v
[Halyard Hub Daemon]
      | (Exclusive Write)
      +---> [ai-sessions.log]
      | (Async Sync)
      +---> [cache.db]
```

### 2.2 Key Architectural Decisions
- **Communication Protocol:** Primary ingestion via OTLP/HTTP (OpenTelemetry) over `localhost:4318`. This allows any tool to emit telemetry without importing Halyard's Python library.
- **Exclusive Writer:** The Hub is the ONLY process that writes to the log when active. This eliminates `flock` contention.
- **Public Direct-Ingest Contract (v4.1):** `/v1/ingest` is the stable
  polyglot API for non-OTLP emitters. It accepts a canonical raw `s ...` line for
  shell/curl integrations and a structured JSON `fields` object for language
  SDKs. Structured ingestion validates required fields and optional metadata
  against Halyard's field registry before converting to `AiSession`.
- **Generated Public Spec (v4.1):** `halyard spec` is generated from the same
  `_FIELDS` registry used by the writer/parser, keeping the documented optional
  key table aligned with the runtime schema.
- **Hub-Managed Active State (v4.2; auth hardened v5.19):** the Hub owns the
  in-memory active timer state while it is running. As of v5.19/B4 **both**
  `GET /v1/state` and `POST /v1/state/timer` require the dashboard token (or an
  AF_UNIX peer-credential) — the read path is authenticated too, because the
  state payload leaks home-directory and project paths. The timer path also
  constrains a client-supplied `project_dir` to a registered project and runs
  the project slug through `_safe_field` (v5.19/B5). A rejected target now
  returns 400 (v5.19/B5-followup) instead of silently falling back to the
  hub's own project — the bare "no target supplied" path still falls back to
  the hub default. The old `~/.halyard/active` file remains the
  compatibility mirror and offline fallback, not a second source of truth
  while the Hub is reachable.
- **Auto-Timer Presence (v4.2):** `POST /v1/state/presence` lets collectors
  record, refresh, and close presence windows through the same Hub state store
  (token/peer-cred authenticated). The Hub worker also closes stale presence
  windows, while `auto_timer.py` retains its historical file path when the Hub
  is unavailable.
- **Reactive Dashboard Events (v4.3; authenticated v5.19):** `/v1/events` is the
  read-only SSE channel for Hub updates. It now requires the token, supplied as
  a `?token=` query param because `EventSource` cannot set headers (the
  dashboard renders the URL with the token; the page itself is auth-gated).
  Concurrent SSE connections are capped to bound worker threads. The Hub emits
  typed events after successful appends and timer state mutations. The Bridge
  dashboard treats these as hints: it fetches the current dashboard HTML and
  patches known `data-hub-fragment` regions instead of reloading the whole page.
- **Localhost Trust Boundary (v5.19):** every Hub endpoint **except**
  `/v1/traces` requires authentication — the bearer token over TCP, or OS
  peer-credential over a new `AF_UNIX` ingest socket (`~/.halyard/hub.sock`,
  `0600`) for same-user machine-to-machine emitters. POST writes require
  `Content-Type: application/json` and reject a cross-site `Sec-Fetch-Site`
  (browser-CSRF / DNS-rebinding defence). Non-finite `cost`/`credits` are
  rejected at the ingest boundary; negative `Content-Length` is rejected
  before any body read (v5.19/B-DoS-clen). `/v1/traces` stays open for the
  token-less Copilot OTLP exporter, bounded by the CSRF rules, the
  finalize-on-eviction accumulator cap, a socket read timeout, and
  per-accumulator caps on `session.id` length and `model_counts`
  cardinality (v5.19/B-DoS-mem) so one session cannot grow memory without
  bound. A forged-timestamp plausibility bound on spans is a tracked
  follow-up, not yet shipped. See `docs/trust-model.md` for the full model.
- **Service Abstraction:** Introduce a `ServiceManager` interface with providers:
  - `LaunchdProvider` (macOS)
  - `SystemdProvider` (Linux)
  - `WindowsServiceProvider` (Windows)
- **Lazy Cache Management:** The Hub updates the SQLite cache in a background thread, separating the capture path from the analytical path.

## 3. Trade-offs
- **Complexity:** Running a background daemon adds a layer of failure (the Hub being down).
- **Fallback:** Tools should gracefully fallback to direct local writes if the Hub is unavailable (maintaining v1-v3 compatibility).
- **Resource Usage:** A persistent Python process uses more idle RAM than ephemeral CLI fires.
- **Schema Strictness:** The structured direct-ingest shape is intentionally
  strict. Extensions can still use canonical log-line forward-compatible
  `key=value` tokens, but the structured public API only advertises keys Halyard
  knows how to validate.
- **Validation Evidence:** v4.1 is covered by `tests/test_v41_polyglot.py`,
  including valid structured ingest, raw-line compatibility, 400 JSON errors,
  unknown-key rejection, generated spec parity, and the reference shell emitter.
- **Timer Compatibility:** v4.2 keeps existing direct file writes as the fallback
  path when `127.0.0.1:4318` is unavailable. Public library functions delegate
  to the Hub first, then fall back to their v1-v4.1 behavior.
- **Validation Evidence:** v4.2 is covered by `tests/test_v42_hub_state.py` and
  the existing start/stop, auto-timer, v4.0 Hub, and v4.1 polyglot focused
  suites. Focused related gate: 36 tests passing.
- **Dashboard Degradation:** SSE is best-effort. If the Hub is down or the
  stream closes, the static dashboard remains usable and no visible in-app error
  is shown.
- **Validation Evidence:** v4.3 is covered by `tests/test_v43_realtime_dashboard.py`
  plus related v4.0-v4.2 Hub and dashboard render suites. Focused related gate:
  58 tests passing.
