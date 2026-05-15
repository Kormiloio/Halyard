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

## In attestable appendices

The planned attestable appendix uses the same trust labels. Signing the appendix
proves the evidence packet matches the local ledger snapshot; it does not turn
allocated or inferred values into captured facts. A verified appendix should
still tell the reader which numbers were measured, calculated, allocated, or
inferred.

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

Protections on that server:

- `Host` is validated against `127.0.0.1`/`localhost` (blocks
  DNS-rebinding); `Origin`/`Referer` are checked when present.
- State-changing actions are POST-only and require a 256-bit token,
  delivered via an `HttpOnly; SameSite=Strict` cookie or the
  `X-Halyard-Token` header, compared in constant time. The token lives
  in a `0600` file under `~/.halyard/`.
- POST bodies are size-capped.

Residual risk: because it is a local server, **another process running
as your user can still reach it** and read the token file. The dashboard
is a convenience surface for the local user, not a security boundary
against local-account compromise.

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
