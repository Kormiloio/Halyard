# Trust Model

Halyard reports include a **trust label** on every cost figure. The label tells you how the number was produced and how much confidence you should have in it. This matters when sharing costs with clients or making decisions based on reported spend.

## Labels

### `captured`

The cost was recorded directly from an API response at session end. The tool reported back the token counts; Halyard applied the pricing table that was current at that moment and stored the result in `ai-sessions.log`.

This is the highest-confidence figure. It is a direct measurement, not a derivation.

**When you see it:** Direct API billing (`billing=api`) — Anthropic API, Google AI Studio, OpenAI API.

---

### `calculated`

The cost was derived from captured token counts using Halyard's local pricing table. The tokens are real; the dollar figure is a calculation.

This is effectively the same as `captured` for practical purposes — the only uncertainty is whether the pricing table was up to date at capture time. Run `halyard update-pricing` regularly to keep it fresh.

**When you see it:** Sessions where tokens were captured but cost was not supplied directly.

---

### `allocated`

The cost is a share of a monthly subscription or seat plan. No per-session cost exists; Halyard divides the monthly plan cost across sessions using the configured allocation rule (`active_minutes`, `session_count`, or `credits`).

Allocated costs are **estimates**, not invoiced charges. They answer: "If I paid $200/month for Claude Max and did 40% of my active minutes on the `acme:auth` project, then roughly $80 of that seat belongs to `acme:auth`."

These figures never appear in `ai-sessions.log`. They are computed at report time and exist only in the analytics layer.

**When you see it:** Seat subscriptions (Claude Max, GitHub Copilot) and credit-based tools (Cursor, Factory) when configured in `ai-plans.toml`.

---

### `inferred`

The project attribution for this session was inferred from an overlapping `time.timeclock` entry rather than being explicitly recorded. The cost figure itself may be captured or allocated — `inferred` refers to the attribution, not the cost.

Use `halyard confirm-attribution` to review and confirm or reject inferred attributions. Once confirmed, the project is written into `ai-sessions.log` and the label becomes `captured` or `allocated`.

**When you see it:** Sessions captured without a `project=` tag that matched an unambiguous timeclock window.

---

### `mixed`

The project has both direct API cost (captured) and allocated seat/credit cost. Halyard shows the breakdown and labels the total `mixed`.

---

### `unallocated`

A seat plan session with `allocation = "manual"` — no automatic allocation was applied. The session is counted but its monetary contribution to the total is zero until you provide manual overrides.

---

## In reports

```
halyard report --ledger
```

Each project row shows its trust label:

```
acme:auth      $58.01  14 sessions  mixed      (some inferred)
acme:dash      $12.34   6 sessions  captured
globex:reports  $0.00   3 sessions  unallocated
```

## In invoices

```
halyard invoice acme --include-ai-evidence
```

The AI evidence appendix groups costs by type and includes a footnote explaining what `allocated` and `inferred` mean. Clients receive an honest picture of what is measured directly versus what is estimated.

## In evidence artifacts and attestable appendices

`halyard evidence` (v2.68, OSS) emits the same appendix as a standalone
artifact plus a keyless `sha256:` digest. Mirroring the v2.40 hash-vs-hmac
distinction: this digest is **tamper-evident** (the author can publish it; anyone
can re-hash the file to detect post-hoc edits) but is **not** a signature and
does **not** prove authorship. The artifact says so in plain text — no
overclaiming. It does not turn allocated or inferred values into captured facts;
the trust labels still tell the reader which numbers were measured, calculated,
allocated, or inferred.

Cryptographic attestation — a *signed*, cross-party-verifiable appendix whose
value is a recipient trusting the signer — is a Halyard Enterprise feature
(`Kormiloio/Halyard-Enterprise`, the moved v2.19), deliberately out of OSS
scope. Signing proves the evidence packet matches the local ledger snapshot; it
still does not reclassify allocated/inferred numbers as captured.

## Design principle

The trust hierarchy exists because client-facing evidence should be honest about what is known versus estimated. A `captured` cost of $12.34 means exactly that. An `allocated` cost of $45.00 means "we believe roughly $45 of the $200 seat cost belongs here, based on how the time was distributed."

Neither is wrong. They are different kinds of information, and Halyard is explicit about which kind you are looking at.

## State-file integrity

Halyard keeps small trusted-state files under `~/.halyard/` (the active
timer, the hub pointer). The `state_integrity` setting in `halyard.toml`
(or the `HALYARD_STATE_INTEGRITY` env override) controls verification.
The guarantees are stated honestly here so the security posture is not
overclaimed:

| Mode | Sidecar | What it actually protects against |
|------|---------|-----------------------------------|
| `off` (default) | none | Nothing. No integrity. |
| `hash` | `.sha256` (unkeyed) | Accidental corruption and naive single-file edits **only**. It is **not** tamper-resistant: an attacker who can write the state file can recompute and rewrite the `.sha256` sidecar. Do not rely on it as a security control. |
| `hmac` | `.hmac` keyed with `~/.halyard/integrity.key` (0600) | Tampering by any process that **cannot read the key file**. It is **not** a defense against a full local-account compromise — an attacker who can read `~/.halyard/integrity.key` can forge a valid sidecar. It raises the bar from "anyone who reads this open-source code" to "an attacker who can also read the 0600 key". |

`hmac` fails closed: if the key is missing or unreadable at verification
time, the read raises an integrity error rather than silently accepting
unverified content.

**Recovery.** Switching `off`/`hash` → `hmac` (or deleting
`integrity.key`) leaves existing state files without a valid `.hmac`
sidecar. The next read fails the integrity check; `halyard` degrades
gracefully (the active-timer / hub lookups return "none" rather than
crashing) and the next write through the Halyard CLI regenerates the key
and sidecar. To reset deliberately, set `state_integrity = "off"`, run a
command that rewrites the state (e.g. start/stop the timer), then
re-enable `hmac`.

## Local dashboard

`halyard dashboard` / the background service run a small HTTP server that
is **bound to `127.0.0.1` only** — it is never exposed beyond the
loopback interface. It is not a remote service and must not be put behind
a public reverse proxy.

Protections on that server (hardened in v5.19):

- `Host` is validated against `127.0.0.1`/`localhost` (blocks
  DNS-rebinding).
- **Browser-CSRF defence:** state-changing requests must send
  `Content-Type: application/json` and must not carry a cross-site
  `Sec-Fetch-Site`. A malicious web page can only issue a CORS *simple
  request* (`text/plain`, form-encoded) without a preflight — those are
  rejected; an `application/json` request from another origin triggers a
  preflight the server never answers.
- **Authentication:** every read/write endpoint the dashboard or hub owns
  (`/v1/ingest`, `/v1/state`, `/v1/events`, `/v1/collisions`,
  `/v1/state/timer`, `/v1/state/presence`, and the dashboard POST actions)
  requires a 256-bit token, compared in constant time. The token is sent
  via the `X-Halyard-Token` header, the `halyard_token` cookie, or — for
  the SSE `EventSource`, which cannot set headers — a `?token=` query
  param on a URL only the authenticated page receives. The dashboard no
  longer hands the token to an unauthenticated `GET`: it is delivered via
  the launch URL, not an unconditional `Set-Cookie`.
- **Token file:** the token lives in a `0600` file under a `0700`
  `~/.halyard/`, created atomically with
  `O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW` (no world-readable window,
  symlink-safe, race-free). A pre-existing token is trusted only if it is
  a regular file owned by the current user.
- **Same-host machine-to-machine ingest:** Halyard's own emitters can reach
  the hub over an `AF_UNIX` socket (`~/.halyard/hub.sock`, `0600`)
  authenticated by OS peer-credential (`SO_PEERCRED` on Linux,
  `getpeereid` on macOS) — a same-user process is trusted with no shared
  secret; a different UID is rejected. TCP loopback (browser, external
  OTLP) continues to use the token.
- **OTLP exception:** `/v1/traces` stays unauthenticated on loopback so the
  zero-config VS Code Copilot OTLP exporter (which cannot send a token)
  keeps working. Its impact is bounded by the loopback `Host` check, the
  `application/json`/`Sec-Fetch-Site` CSRF rules, a finalize-on-eviction
  accumulator cap, and a socket read timeout. (A forged-timestamp
  plausibility bound on spans is a tracked follow-up, not yet shipped — a
  same-user process could otherwise inject telemetry with implausible
  timestamps.)
- POST bodies are size-capped; concurrent SSE connections are bounded.

Residual risk: a co-located process running **as your own user** can read
the `0600` token file and authenticate, and can connect to the `AF_UNIX`
socket (same UID). The dashboard defends against *other local users* and
browser-origin CSRF/DNS-rebinding, but it is not a security boundary
against compromise of your own account.

## Files Halyard writes

Halyard creates or appends to these user-owned files. It **preserves
existing keys** (it merges, it does not template over your config) and
**refuses to overwrite a file that exists but does not parse as JSON**
(it errors with an actionable message instead of destroying it):

- `~/.claude/settings.json` and `<project>/.claude/settings.json` —
  Claude Code hook entries.
- `~/.gemini/settings.json` — Gemini CLI hook entries.
- `~/.cursor/hooks.json` — Cursor hook entries.
- `<project>/.vscode/tasks.json` — VS Code manual-capture tasks.
- `<project>/halyard.toml`, `clients.toml`, `projects.toml`,
  `time.timeclock`, `ai-sessions.log`, `ai-plans.toml`,
  `.gitignore` — created by `halyard init` in the project directory.
- `~/.halyard/` — `active`, `hub`, optional integrity sidecars/key,
  the dashboard token, the SQLite read cache.

Halyard never writes outside the user's home, the project directory, or
the system temp dir.
