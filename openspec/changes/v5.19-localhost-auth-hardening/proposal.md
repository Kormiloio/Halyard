# v5.19 — Localhost auth & secret hardening

## Why

The pre-release audit (`docs/reviews/2026-06-pre-release-audit.md`) found the
localhost HTTP surface does not enforce its own trust boundary. These five
high blockers are the shared-host / CSRF attack surface and are the last
launch gate (the owner confirmed shared hosts — CI, devcontainers, cloud
workstations — are in scope):

- **B2** — `_load_or_create_token()` is unsafe end to end: writes the secret
  to a predictable temp under default umask before chmod (world-readable
  window + symlink pre-placement), trusts any pre-existing 64-hex token with
  no ownership check, races on the shared temp path, and swallows the
  corrective chmod error.
- **B3** — the dashboard hands the token to *any* unauthenticated GET via
  `Set-Cookie`, so a co-located user `curl`s the page and harvests it; this is
  also how the legitimate browser currently obtains it.
- **B4-auth** — `/v1/ingest`, `/v1/traces`, and `/v1/events` run only
  `_host_ok()` (a DNS-rebinding-bypassable Host allowlist), never
  `_authorized()`; any local process forges ledger writes or pins threads.
- **B5** — `/v1/state/timer action=start` accepts an attacker-controlled
  `project_dir` and writes `time.timeclock` into any existing directory, with
  the raw `project` string (no `_safe_field`) injected into the log line.
- **B13** — the state-integrity mode is resolved through the
  attacker-controlled pointer, so an attacker can downgrade HMAC to hash/off
  and bypass integrity verification.

## Threat model & mechanism (decided with the owner)

Two distinct threats need two defenses:

1. **Malicious local webpage driving the browser (CSRF / DNS-rebinding).**
   Only a **bearer token** defends this — a cross-origin page cannot read the
   0o600 token file nor set the `X-Halyard-Token` header. Peer-credentials
   can't help (the browser is the user's own UID).
2. **Another local user on a shared host.** A **0o600 token file** already
   gates this (a co-user cannot read the credential), and on the
   machine-to-machine path we additionally add **real OS peer-credential
   auth over an AF_UNIX socket** (`SO_PEERCRED` on Linux, `getpeereid` on
   macOS), which TCP cannot provide.

So: **token everywhere (browser + machine), plus a new AF_UNIX ingest
listener with peer-cred auth for same-host emitters.** The browser keeps
TCP+token; external OTLP exporters (which speak HTTP/TCP) keep TCP+token.

## What changes

- **B2:** create the token with `os.open(path, O_CREAT|O_EXCL|O_WRONLY|
  O_NOFOLLOW, 0o600)` — secure mode at creation (no world-readable window),
  symlink-safe (`O_NOFOLLOW`), race-free (`O_EXCL`: exactly one creator;
  losers read the winner's token). Create `~/.halyard` `0o700`. Adopt a
  pre-existing token only if `st_uid == os.getuid()` and it is not
  group/other-writable; otherwise recreate. Do not `suppress` the corrective
  chmod — fail closed. Guard `getuid`/`O_NOFOLLOW` for Windows.
- **B3:** stop issuing the token to unauthenticated GETs. `run_dashboard`
  opens the browser at `http://localhost:PORT/?token=<tok>`; the server sets
  the auth cookie **only** when a request presents the valid token (URL or
  header/cookie). A passive GET without the token gets no cookie and no
  privileged action.
- **B4-auth (TCP):** run `_authorized()` on `/v1/ingest`, `/v1/events`, and
  `/v1/state` — the endpoints Halyard controls; cap concurrent SSE
  connections and add an idle timeout; `hub_client.ingest_line` sends
  `token=True`.
  - **`/v1/traces` decision (owner, 2026-06-05):** this endpoint is fed by
    VS Code Copilot's built-in OTLP exporter, which Halyard configures with
    only `otlpEndpoint`/`exporterType` — it **cannot** send an
    `X-Halyard-Token` header. Requiring auth would break zero-config Copilot
    telemetry with no config path to fix it. So `/v1/traces` stays
    **unauthenticated but loopback-only**, with its *impact* bounded: the
    v5.18 slowloris timeout + cardinality-cap-that-finalizes already apply,
    and we add a **forged-timestamp plausibility bound** (reject spans whose
    start/end fall far outside a sane window). The residual risk — a
    co-resident local process forging Copilot-shaped telemetry — is
    documented in the changeset and SECURITY notes. (`hub_client` does not
    POST traces; it is OTLP-emitter-only.)
- **B4-auth (AF_UNIX, new):** add a Unix-domain-socket listener
  (`~/.halyard/hub.sock`, mode 0o600 in the 0o700 dir) for same-host ingest;
  authenticate by peer-cred (`peer_uid == os.getuid()`). `hub_client` prefers
  the socket where available and falls back to TCP+token (Windows / no
  socket). External OTLP exporters are unaffected (they keep TCP+token).
- **B5:** constrain `_target_project_dir` to a registered-project allowlist
  (reject paths outside known roots; refuse to *create* `time.timeclock` in an
  untracked dir) and run `project` through `_safe_field` on the timer path.
- **B13:** anchor the integrity mode to a trusted source — if an `.hmac`
  sidecar exists for a file, require HMAC verification regardless of any
  `state_integrity` value resolved through the untrusted pointer; never
  silently downgrade hmac → hash/off.

## Out of scope

- Replacing the Host-allowlist with a full Origin/CSRF token on every browser
  POST beyond the existing HMAC token (the token + same-origin already covers
  the audited vector); revisit only if a new finding warrants it.
- Windows AF_UNIX (available only on Win10 1803+ and not for this use); the
  TCP+token fallback covers Windows.

## Success criteria

- Token file is created 0o600 with no world-readable window, symlink-safe,
  and race-free; a planted/other-owned token is not trusted.
- A co-located user cannot harvest the token via GET, nor forge ledger writes
  or timer state.
- Same-host emitters authenticate over the AF_UNIX socket by peer-cred;
  Windows falls back to TCP+token.
- HMAC cannot be downgraded via attacker-controlled config.
- Full suite green; ruff + mypy clean. Each fix has a regression test.
