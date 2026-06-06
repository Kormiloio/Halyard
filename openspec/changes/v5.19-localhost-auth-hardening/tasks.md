# v5.19 — Tasks

Source: `docs/reviews/2026-06-pre-release-audit.md`. Implemented by the human
integrator (auth-critical, design-sensitive — done sequentially, not
parallelized). Owner-approved design: token everywhere + AF_UNIX peer-cred
ingest listener.

## B2 — token lifecycle [service.py] ✅

- [x] `_load_or_create_token`: create via
      `os.open(O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW, 0o600)` (no temp, no
      world-readable window, symlink-safe, race-free). `_force_replace_token`
      handles an untrusted occupant (EEXIST/ELOOP).
- [x] `~/.halyard` created `0o700` (`_ensure_halyard_dir`).
- [x] Adopt a pre-existing token only if `st_uid == getuid()` and regular
      file; tighten loose perms fail-closed (chmod not suppressed)
      (`_read_token_if_ours`, uses `lstat`).
- [x] Windows guards (`hasattr(os, "getuid")`, `_O_NOFOLLOW` fallback to 0).
- [x] Regression test (tests/test_v519_b02_token_lifecycle.py, 8 tests):
      0o600 file + 0o700 dir; garbage/planted-symlink rejected & victim
      untouched; loose perms re-tightened; no leftover temp; stable adopt.

## Peer-cred helper [src/halyard/peercred.py] ✅

- [x] `peer_uid(sock) -> int | None` via `SO_PEERCRED` (Linux) / `getpeereid`
      (macOS, ctypes with explicit signature); AF_UNIX-guarded; None elsewhere.
- [x] `peer_is_self(sock) -> bool` (fails closed without `os.getuid`).
- [x] Unit test (tests/test_v519_peercred.py, 4 tests): AF_UNIX pair → self;
      non-unix → None; Windows-sim fails closed.

## B4-auth — TCP endpoints [hub_server.py, hub_client.py, dashboard.py] ✅

- [x] Transport-aware `_authorized()`: AF_UNIX peer → `peer_is_self`; TCP →
      bearer token via `X-Halyard-Token` header, `halyard_token` cookie, **or
      `?token=` query param** (EventSource cannot set headers).
- [x] `_authorized()` guards on `/v1/ingest`, `/v1/state`, `/v1/collisions`,
      and `/v1/events` (`/health` stays open).
- [x] `/v1/traces` stays unauthenticated (loopback) for Copilot OTLP compat.
- [x] **Browser-CSRF hardening (owner finding #1):** `_csrf_ok()` requires
      `Content-Type: application/json` on every POST (a cross-origin CORS
      "simple request" can only be text/plain/form-encoded → blocked; JSON
      forces a preflight the hub never answers) and rejects
      `Sec-Fetch-Site: cross-site`. Applied in `do_POST` (covers ingest +
      the open `/v1/traces`). Machine clients already send application/json.
- [x] `_MAX_SSE_CONNECTIONS` cap (32) via `_sse_acquire`/`_sse_release`.
- [x] `hub_client.ingest_line`/`read_state`/`check_collisions` send
      `token=True`; `dashboard.py` renders the SSE URL with `?token=`.
- [x] Updated 5 existing hub test files (v4/v41/v42/v43/v5-collision) to send
      the token; 87 hub blast-radius tests green.
- [ ] Forged-timestamp plausibility bound on `/v1/traces` — deferred (minor;
      `/v1/traces` only writes telemetry, and the v5.18 cap/timeout already
      bound impact). Tracked as a follow-up.

### Regression test for the CSRF / auth surface ✅

- [x] `tests/test_v519_b04_auth.py` (8 tests): unauth ingest → 401; valid
      token → 200; text/plain → 415; `Sec-Fetch-Site: cross-site` → 415;
      `/v1/state` unauth → 401; SSE `?token=` → 200; SSE no-token → 401;
      `/health` stays open. Full suite incl. TUI green.

## B4-auth — AF_UNIX ingest listener (new) [hub_server.py, hub_client.py] ✅

- [x] `_ThreadingUnixHTTPServer` (ThreadingMixIn + UnixStreamServer) on a
      **port-keyed** socket `~/.halyard/hub-{port}.sock` (0o600, dir 0o700),
      reusing the same `_Handler` → identical routing/auth. Port-keying stops a
      test hub (:54318) from clobbering a real hub (:4318).
- [x] Authenticates by peer-cred via the transport-aware `_authorized()`
      (`peer_is_self`); `_host_ok()` skips the Host check for AF_UNIX (no
      browser/DNS). No token required on the socket.
- [x] `hub_client` prefers the socket (`_UnixHTTPConnection`, port-keyed
      `_unix_socket_path`; skipped on Windows / `HALYARD_HUB_HOST` override);
      falls back to TCP+token only on a *connection* failure.
- [x] Lifecycle: `_start_unix_listener` (best-effort; never blocks TCP) unlinks
      a stale socket then binds + chmods 0o600; `stop()` shuts it down and
      unlinks. POSIX-only (`_AF_UNIX_AVAILABLE`).
- [x] Regression test (tests/test_v519_afunix_listener.py, 3 tests): socket
      0o600 + removed on stop; ingest over the socket with **no token**
      succeeds (peer-cred) and writes the ledger; CSRF Content-Type still
      enforced. Broader hub suite (75 tests) unaffected.

## B3 — token disclosure [dashboard.py] ✅

- [x] `_send_dashboard` sets the `halyard_token` cookie ONLY when the request
      already presents the valid token (`_request_token_valid()`: launch-URL
      `?token=`, `X-Halyard-Token` header, or existing cookie; constant-time).
- [x] `run_dashboard` opens the browser at `…/?token=<tok>` so the legit user
      is authed on first load and receives the cookie for subsequent POSTs.
- [x] Regression test (tests/test_v519_b03_token_cookie.py, 4 tests):
      unauth GET → no `Set-Cookie` (no token leak); `?token=` / valid cookie →
      cookie set; wrong token → no cookie. 53 dashboard tests still green.
- Note (separate, lesser, follow-up): an unauthenticated GET still *renders*
      the page (data visible), only the token is withheld. Gating the page
      body on auth is a larger change tracked separately; the audited
      escalation (token → writes) is closed.

## B5 — timer path traversal [hub_server.py] ✅

- [x] `_target_project_dir` constrained to the `read_registry()` allowlist
      (resolved-path match); unregistered dirs return None → caller falls back
      to the hub's own project dir. The timeclock-parent fallback is
      constrained the same way.
- [x] `project` run through `_safe_field` on the timer path (mirrors presence).
- [x] Regression test (tests/test_v519_b05_timer_path.py, 3 tests): arbitrary
      `project_dir`/`timeclock` rejected; registered accepted. 83 existing
      hub/timer tests still green.

## B13 — HMAC downgrade [state_integrity.py] ✅

- [x] Sidecar-as-strength-floor enforced at the verification choke point
      (`read_trusted_state`): `_MODE_STRENGTH` map; if a stronger sidecar
      exists than the resolved mode, verify with the stronger scheme. The old
      `mode == "off"`-only guard in `read_global_trusted_state` is subsumed
      (simplified). Protects every caller, not just the global entry point.
- [x] Regression test (tests/test_v519_b13_hmac_downgrade.py, 2 tests): forged
      content + unkeyed `.sha256` + `mode="hash"`/`"off"` is rejected because
      the `.hmac` sidecar forces HMAC; genuine hash-only file still reads. 43
      existing integrity tests green.

## Gate ✅

- [x] `uv run pytest` (full suite **incl. TUI**) green.
- [x] `uv run ruff check .` + `ruff format --check .` clean.
- [x] `uv run mypy src/` clean.
- [x] Roadmap entry (project.md #90); audit report §0 → all 23 blockers fixed,
      AF_UNIX listener done, nothing outstanding.
