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

## B4-auth — TCP endpoints [hub_server.py, hub_client.py]

- [ ] `_authorized()` on `/v1/ingest`, `/v1/events`, `/v1/state` (the
      Halyard-controlled endpoints). Transport-aware: AF_UNIX → peer-cred,
      TCP → token.
- [ ] `/v1/traces` stays unauthenticated (loopback-only) for Copilot OTLP
      compat; add a forged-timestamp plausibility bound instead.
- [ ] **Browser-CSRF hardening (owner review, finding #1):** a cross-origin
      `text/plain` POST is a CORS "simple request" — it reaches the hub with
      no preflight, so even a plain malicious webpage (not just DNS-rebinding)
      can forge writes. On the write endpoints, **require
      `Content-Type: application/json`** and **reject requests carrying a
      browser `Origin`/`Sec-Fetch-Site: cross-site`**. This also hardens the
      deliberately-open `/v1/traces` against browser CSRF without breaking
      Copilot (its OTLP exporter sends neither a browser Origin nor
      text/plain). Add a hostile-origin regression test.
- [ ] Cap concurrent SSE connections + idle timeout on `/v1/events`.
- [ ] `hub_client.ingest_line` sends `token=True`.
- [ ] Regression tests.

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
