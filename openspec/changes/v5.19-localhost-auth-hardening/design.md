# v5.19 — Design

## Two threats, two mechanisms

| Threat | Defense | Why |
|---|---|---|
| Malicious local webpage drives the browser (CSRF / DNS-rebinding) | Bearer token (`X-Halyard-Token` / cookie) + loopback Host allowlist | A cross-origin page can't read the 0o600 file or set the header. Peer-cred can't help — the browser is the user's own UID. |
| Another local user on a shared host | 0o600 token file **and** AF_UNIX peer-cred on the machine-to-machine path | A co-user can't read the token; on the Unix socket their UID ≠ ours. |

The token and peer-cred are complementary, not redundant — they defend
different attackers. TCP can't carry peer-cred (it's AF_UNIX-only), which is
why the machine-to-machine ingest gets its own Unix socket.

## B2 — secure token creation (done)

`os.open(path, O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW, 0o600)`: mode is set *at
creation* (no world-readable window), `O_NOFOLLOW` defeats a pre-placed
symlink, `O_EXCL` makes exactly one process the creator so concurrent
first-run callers converge (losers re-read the winner's token). `~/.halyard`
is forced to `0o700`. A pre-existing token is adopted only if it is a regular
file owned by us (`lstat` + `st_uid == getuid()`); loose perms are tightened
fail-closed. Windows: `getuid`/`O_NOFOLLOW` are guarded (token-only model).

## Peer-cred helper (done)

`peercred.peer_uid(sock)` → `SO_PEERCRED` (Linux) / `getpeereid` (macOS,
ctypes with explicit signature), AF_UNIX-guarded, `None` elsewhere.
`peer_is_self(sock)` fails closed when the UID can't be determined.

## Transport-aware auth (the key seam)

A single change to the handler's `_authorized()`:

```
if self.connection.family == socket.AF_UNIX:
    return peercred.peer_is_self(self.connection)   # same-user emitter
return <existing token check>                        # TCP browser / emitter
```

So one `_Handler` serves both listeners; the transport decides the
credential. We then add `_authorized()` guards to the endpoints that lacked
them.

## Endpoint auth matrix (B4-auth)

| Endpoint | TCP | AF_UNIX | Notes |
|---|---|---|---|
| `/v1/ingest` | token | peer-cred | Halyard's polyglot emitters; `hub_client` now sends `token=True` |
| `/v1/events` (SSE) | token | n/a | + concurrent-connection cap + idle timeout |
| `/v1/state` (GET) | token | peer-cred | leaks home/project paths — must be authed |
| `/v1/state/timer`,`/presence` | token (already) | peer-cred | unchanged auth; B5 hardens the timer path |
| `/v1/traces` (OTLP) | **open** (loopback) | n/a | Copilot exporter can't send a token; bound impact via timestamp plausibility + v5.18 caps/timeout |

## AF_UNIX ingest listener (B4-auth, new)

A second listener on `~/.halyard/hub.sock` (0o600 in the 0o700 dir) using a
`socketserver.ThreadingUnixStreamServer` + the same `BaseHTTPRequestHandler`
subclass. `BaseHTTPRequestHandler` needs minor accommodation for AF_UNIX
(no `(host, port)` peer tuple): override `address_string()`/`client_address`
handling. The Hub runs both servers (TCP + Unix) on daemon threads; the Unix
socket file is unlinked on stop and a stale socket from a crashed run is
removed on start. `hub_client` prefers the socket when it exists and is
connectable, falling back to TCP+token otherwise (always on Windows).

## B3 — token-to-browser handoff

Stop issuing the token to an unauthenticated GET via `Set-Cookie`.
`run_dashboard` opens the browser at `…/?token=<tok>`; the dashboard sets the
auth cookie **only** when a request already presents the valid token (URL
param, header, or existing cookie). A passive GET from another local user —
who lacks the token — receives no cookie and can drive no privileged action.

## B5 — timer path traversal

`_target_project_dir(data)` must reject a `project_dir` outside the registered
projects (and refuse to *create* `time.timeclock` in an untracked dir), and
the `project` string must go through `_safe_field` on the timer path exactly
as the presence path already does.

## B13 — HMAC downgrade

The integrity mode must not be resolved through the attacker-controlled
pointer. If an `.hmac` sidecar exists for a file, require HMAC verification
regardless of any `state_integrity` value reached via downstream config —
never silently downgrade hmac → hash/off.

## Testing

Per-blocker regression tests; the AF_UNIX path is exercised by connecting a
client socket to the live socket and asserting a same-uid peer is accepted and
an ingest writes the ledger. Windows paths assert the token fallback.
