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

## B4-auth — AF_UNIX ingest listener (new) [hub_server.py, hub_client.py]

- [ ] AF_UNIX `ThreadingHTTPServer`-style listener on `~/.halyard/hub.sock`
      (0o600, in 0o700 dir); same ingest routing as TCP.
- [ ] Authenticate by peer-cred (`peer_is_self`); no token required on socket.
- [ ] `hub_client` prefers the socket where present, falls back to TCP+token.
- [ ] Lifecycle: create/unlink socket on start/stop; handle stale socket file.
- [ ] Regression test: same-uid peer accepted; ingest via socket writes ledger.

## B3 — token disclosure [dashboard.py, service.py?]

- [ ] Remove unconditional `Set-Cookie` on unauthenticated GET.
- [ ] `run_dashboard` opens browser at `…/?token=<tok>`; cookie issued only on
      a valid-token request (URL/header/cookie).
- [ ] Regression test: GET without token → no `Set-Cookie`, no privileged
      action; GET with token → cookie set; POST still requires the token.

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

## Gate

- [ ] `uv run pytest --ignore=tests/test_tui.py` green.
- [ ] `uv run ruff check .` + `ruff format --check .` clean.
- [ ] `uv run mypy src/` clean.
- [ ] Roadmap entry; audit report §0 → all 23 blockers fixed.
