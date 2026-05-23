# Spec: Dashboard Authentication

## Token file

Location: `~/.halyard/dashboard.token`
Format: 32 bytes hex (64 chars) on a single line, no trailing newline.
Permissions: `0600`. Owner-only read/write.

Generated on first run of either `halyard service install` or
`halyard dashboard` (foreground). Reused on subsequent runs.

## Request validation order

For every `POST` to any path under `/api/`:

1. **Host validation.** The `Host` header must equal `<bound_host>:<bound_port>`.
   If absent or mismatched, return `400 Bad Request` with body
   `{"error":"invalid host"}`.

2. **Origin/Referer validation.** If `Origin` or `Referer` is present and
   does not match the server's own origin, return `403 Forbidden` with
   body `{"error":"cross-origin denied"}`.

3. **Token validation.** Read token from one of:
   - `Cookie: halyard_token=<value>`
   - `X-Halyard-Token: <value>` header
   If neither matches the contents of `~/.halyard/dashboard.token`,
   return `401 Unauthorized` with body `{"error":"missing token"}`.

4. **Content-Length cap.** If `Content-Length` is missing or exceeds
   8192 bytes, return `413 Payload Too Large` with body
   `{"error":"payload too large"}`.

After all four pass, the request body is read and the start/stop logic
runs.

## Cookie issuance

For `GET /` and `GET /index.html`, the response includes:

```
Set-Cookie: halyard_token=<value>; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000
```

(30-day expiration; renewed on each page load.)

`HttpOnly` prevents JS access from any tab. `SameSite=Strict` means the
cookie is not sent on cross-origin requests, so a drive-by webpage
cannot include it in a forged POST.

## Token rotation

To rotate, the user runs:

```bash
halyard service uninstall
halyard service install
```

`uninstall` deletes `~/.halyard/dashboard.token` if present.
`install` regenerates it. Browser cookies remain stale and the user
re-loads the dashboard, picking up a fresh cookie.

There is no in-product rotation command in v2.16.

## Threat model assumptions

| Threat                                            | Defense                              |
|---------------------------------------------------|--------------------------------------|
| Drive-by webpage POSTs to dashboard               | SameSite cookie + Origin check       |
| DNS rebinding to bypass localhost binding         | Host header validation               |
| Local user reading another user's token           | File mode `0600`                     |
| Process on same machine forging requests          | Out of scope (full machine = compromise) |
| Network attacker on same wifi                     | Bind to `127.0.0.1` only             |
| User installs hostile browser extension           | Out of scope                         |

## What this does NOT defend

- Other processes running as the same user on the same machine. They can
  read the token file and forge anything. Halyard's threat model is
  network and browser-tab attackers, not local-process attackers.
- Compromised browser. If the user's browser is owned, the attacker has
  the cookie too.
