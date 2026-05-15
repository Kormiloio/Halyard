# v2.35 — Subscription Cost Allocation

## Problem

Most serious AI users are on subscription plans, not pay-per-token APIs:

- Claude Pro / Claude Max — flat monthly fee
- Codex (OpenAI) — flat monthly fee
- Gemini Advanced — flat monthly fee
- GitHub Copilot — flat monthly fee

For these users, Halyard captures token counts but shows **$0.00** for cost.
This is technically correct (no API spend was incurred) but practically useless.
The user spent real money — they just pre-paid it. "$0.00" makes Halyard feel
broken and provides no insight into the actual value or intensity of AI usage.

What the user actually wants to know:
- "I'm paying $200/month for Claude — how much of that value am I getting?"
- "Across all my subscriptions I spend $240/month — what is each tool worth?"
- "When I invoice a client, what AI cost should I allocate to this project?"

## Proposed model

### Plan definition (new: `ai-plans.toml`)

The user declares their subscription plans in `ai-plans.toml` in the project
(or hub) directory:

```toml
[[plan]]
tool = "claude-code"
label = "Claude Max"
monthly_usd = 200.00
started = "2026-01-01"

[[plan]]
tool = "codex"
label = "OpenAI Pro"
monthly_usd = 20.00
started = "2026-03-01"

[[plan]]
tool = "gemini-cli"
label = "Gemini Advanced"
monthly_usd = 19.99
started = "2026-02-01"
```

This file is already partially supported by the ledger module (`read_ai_plans`
exists). This change makes it first-class on The Bridge and in `halyard report`.

### Cost display

When a plan is defined for a tool and the captured API cost is $0.00, display
the **allocated cost** instead, with a trust label:

| Situation | Display | Trust label |
|---|---|---|
| API cost captured | $12.34 | captured |
| Plan defined, tokens available | $47.20 *(allocated)* | allocated |
| Plan defined, no tokens | $200.00 *(plan cost)* | plan |
| No plan, no API cost | $0.00 | missing |

**Allocation formula (tokens available):**

```
allocated_cost = (session_tokens / month_total_tokens) × plan_monthly_usd
```

This distributes the monthly plan cost across sessions in proportion to token
usage. A project that consumed 40% of your Claude tokens this month is allocated
40% of the $200 plan cost.

**Allocation formula (no tokens):**

Fall back to session-count-weighted allocation:

```
allocated_cost = (project_sessions / month_total_sessions) × plan_monthly_usd
```

### Dashboard changes

- AI Cost card shows allocated cost (with "allocated" sub-label) when plan is
  defined and captured cost is $0.00.
- Cost Allocation panel (already exists for ledger) shows both captured and
  allocated columns.
- A new summary line: "Plan spend: $239.99/mo across 3 tools."
- Trust label is shown next to every cost figure so the user always knows the
  data quality.

### CLI changes

- `halyard report` shows allocated cost alongside captured cost.
- New flag `--show-plans` on `halyard report` shows plan definitions and
  utilisation summary.

### Invoicing

When `halyard invoice` generates an invoice, it can include allocated AI cost
as a line item (with the "allocated" trust label so clients understand the basis).

## What this is not

- Not a budget enforcement system (that is `halyard budget`, already shipped).
- Not pay-per-token calculation for subscription tools — it is proportional
  allocation of a known flat cost.
- Not written to `ai-sessions.log` — allocation is a read-time computation.

## Success criteria

- A user with a $200/month Claude plan sees a plausible non-zero cost figure
  on The Bridge.
- The trust label always makes the distinction clear between captured and
  allocated cost.
- A user with no plans configured sees no change from current behaviour.
- `ai-plans.toml` already supported by the ledger module — this is a display
  and first-class-treatment change, not a new format.
