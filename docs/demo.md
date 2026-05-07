# 60-Second Demo: Human Time + AI Cost by Project

This walkthrough shows a freelancer setting up Halyard for a client project, capturing AI usage, and generating an invoice with AI evidence.

## Prerequisites

```bash
pipx install halyard
```

---

## Step 1 — Initialize a project (10s)

```bash
mkdir ~/consulting/acme-auth && cd ~/consulting/acme-auth
halyard init
```

Edit `clients.toml` and `projects.toml` to define your client and project:

```toml
# clients.toml
[[client]]
slug = "acme"
name = "Acme Corp"
hourly_rate = 150
email = "billing@acme.example"
```

```toml
# projects.toml
[[project]]
slug = "auth"
client_slug = "acme"
name = "Auth migration"
```

---

## Step 2 — Configure your AI plans (10s)

Edit `ai-plans.toml` (created by `halyard init`) to describe how you pay for AI tools:

```toml
[[plan]]
slug = "claude-max"
tool = "claude-code"
billing = "seat"
monthly_usd = 200
allocation = "active_minutes"
starts_on = "2026-01-01"

[[plan]]
slug = "cursor-pro"
tool = "cursor"
billing = "credits"
monthly_usd = 20
credit_to_usd = 0.04
allocation = "credits"
starts_on = "2026-01-01"
```

See [`docs/samples/ai-plans.toml`](samples/ai-plans.toml) for a full example.
See [`docs/samples/ai-sessions.log.sample`](samples/ai-sessions.log.sample) for example log entries.

---

## Step 3 — Install hooks (5s)

Hooks auto-capture every AI session to `ai-sessions.log`:

```bash
halyard install-hook          # Claude Code
halyard install-cursor-hook   # Cursor
halyard install-gemini-hook   # Gemini CLI
```

From this point on, every AI session is captured automatically.

---

## Step 4 — Track human time (5s)

```bash
halyard start acme:auth       # clock in
# ... do the work ...
halyard stop                  # clock out
halyard status                # check active timer
```

---

## Step 5 — Check your report (10s)

```bash
halyard report
```

Shows human time and AI usage for the current month:

```
Report — May 2026
────────────────────────────────────────────────
  Human time  3h 20m  this month  (today: 1h 45m)
  AI sessions  14
  AI cost      $0.73
  Tokens       in 93,420  out 14,203

By project
  acme:auth                        $0.48  9 sessions
  acme:dash                        $0.25  5 sessions

By model
  claude-sonnet-4-6                $0.00  10 sessions
  gpt-4o                           $0.00   2 sessions
  gemini-2.5-pro                   $0.48   2 sessions
```

Add `--ledger` to see seat and credit costs allocated by project:

```bash
halyard report --ledger
```

```
AI Work Ledger — May 2026
  Direct API  $0.73  Allocated  $44.20  Total  $44.93

  acme:auth      $32.14  9 sessions  mixed
  acme:dash      $12.79  5 sessions  mixed
```

---

## Step 6 — Confirm inferred attribution (5s)

Sessions captured without an explicit project tag get attribution inferred from overlapping timeclock entries. Review and confirm them:

```bash
halyard confirm-attribution
```

```
3 session(s) with inferred attribution

  2026-05-07 13:00 → 13:28  (28m)
  claude-code / claude-sonnet-4-6  $0.00
  Inferred: acme:auth
  [y]es / [n]o / [s]kip: y

1 session(s) attributed.
  2 skipped
```

---

## Step 7 — Set budget alerts (5s)

```bash
halyard set-budget acme --daily 15.00 --monthly 300.00
halyard budget
```

---

## Step 8 — Invoice with AI evidence (10s)

```bash
halyard invoice acme --period 2026-05 --include-ai-evidence
```

This generates `invoices/2026-05-001-acme.md` with an AI Usage Evidence appendix:

```markdown
---

## AI Usage Evidence

**Period:** May 2026
**Tools:** claude-code, cursor, gemini-cli
**Models:** claude-sonnet-4-6, gpt-4o, gemini-2.5-pro

| Metric | Value |
|---|---|
| Sessions | 14 |
| Active minutes | 312 |
| Input tokens | 93,420 |
| Output tokens | 14,203 |

| Cost | Amount | Basis |
|---|---|---|
| Direct API | $0.7300 | captured from API responses |
| Allocated plans | $44.2000 | subscription plan allocation |
| **Total AI cost** | **$44.9300** | |

*Allocated costs are estimates derived from configured subscription plans
and are not direct per-session charges.*
```

---

## What you now have

- `ai-sessions.log` — every AI session, append-only, plain text
- `time.timeclock` — human time in hledger-compatible format
- `invoices/2026-05-001-acme.md` — invoice with AI evidence appendix
- Full cost breakdown: direct API + allocated seat/credit plans

For a deeper explanation of what `captured`, `allocated`, and `inferred` mean, see [`docs/trust-model.md`](trust-model.md).
