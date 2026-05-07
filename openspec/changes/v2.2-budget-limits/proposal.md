# Proposal: v2.2 — Budget Limits

## Why this change

Halyard captures AI spend accurately. But capture without feedback is an
odometer without a fuel gauge — you know how far you've gone, only after
you've already run out.

A developer with a $50/day API budget working on a tight-margin engagement
currently has no way to know they've crossed it until they run `halyard report`
at the end of the day. By then the cost is sunk.

The right intervention is a warning surfaced at the moment AI work is about
to happen — before the next session starts, not after it ends.

## What this change does

### 1. Budget configuration

Per-project limits defined in the project's `halyard.toml`:

```toml
[budget]
daily_usd   = 50.00   # warn when today's AI spend exceeds this
monthly_usd = 500.00  # warn when this month's AI spend exceeds this
```

Both fields are optional. Either or both can be set. No budget configured =
no warnings (existing behaviour preserved).

### 2. Warning mechanism

Budget checks run in the **`UserPromptSubmit` hook** for Claude Code (and
equivalent "before prompt" hooks for Cursor and Gemini CLI). This fires
*before* the session starts — the only point where a warning is useful.

When a limit is exceeded, the hook writes a warning to stdout. Claude Code
displays hook stdout to the user before proceeding:

```
⚠  Halyard budget warning: today's AI spend is $52.30, which exceeds your
   daily limit of $50.00 for acme:auth-migration. The session will proceed.
   Run `halyard report` to review your spend.
```

The session **always proceeds**. Halyard warns; it does not block. Blocking
would require hooking into the tool's session lifecycle in ways that are
fragile, tool-specific, and contrary to the UX principle that capture should
be invisible.

### 3. `halyard budget` command

A new CLI command that shows current spend against configured limits:

```
$ halyard budget

Budget status — May 2026
─────────────────────────────────────────
  acme:auth-migration
    Today      $52.30 / $50.00  ⚠ over
    This month $312.00 / $500.00  ✓

  globex:reporting
    Today      $8.10  / $50.00   ✓
    This month $41.20 / $500.00  ✓
```

### 4. Scope of "spend" in the budget check

Budget checks count **direct API cost only** (`billing=api` sessions with
`cost_usd > 0`). Seat and credits sessions (`billing=seat`, `billing=credits`)
are excluded — those costs are not per-session and would produce misleading
warnings.

This is the conservative choice. A future version could let users include
allocated plan costs in the budget calculation.

## What this change does NOT do

- **No hard blocks.** Sessions always proceed. A blocking mechanism would
  require deep tool integration and raise UX questions (what does the user
  see? how do they override?) that are out of scope here.
- **No team budget enforcement.** Org-level budget governance is a v3 concern.
  This is per-developer, per-project, local only.
- **No budget for seat/credits tools.** Cursor and Copilot have no meaningful
  per-session cost to check against.
- **No push notifications or OS alerts.** The warning surfaces in the tool's
  UI via the hook stdout channel — no separate notification infrastructure
  needed.
- **No automatic budget reset** beyond the natural daily/monthly window
  implied by the field names.

## Key decisions

**Why warn at session start (UserPromptSubmit) rather than session end (Stop)?**  
A warning after the session ends is useless — the cost is already incurred.
A warning before the session starts gives the developer a chance to pause,
switch models, switch projects, or decide the work can wait. This is the only
point in the lifecycle where the warning has action value.

**Why warn-only and not block?**  
Because blocking a developer's workflow mid-task is a high-cost intervention.
A blocked session means lost context, interrupted flow, and potential for data
loss. The risk of silently exceeding a budget limit by one session is much
lower than the cost of a false-positive block. Start with warnings; consider
opt-in blocking in a later version if users ask for it.

**Why `halyard.toml` and not a separate `budgets.toml`?**  
Budget limits are project-level configuration, not a separate concern. Putting
them in `halyard.toml` keeps related config together and avoids file sprawl.
The `[budget]` section is optional — projects without it behave identically to
today.

**Why daily and monthly, not hourly or per-session?**  
Daily and monthly match how developers think about AI spend: "I've already
spent a lot today" or "I'm burning through my monthly budget on this project."
Hourly limits would fire too frequently for normal work; per-session limits
would need a separate threshold-setting UX.

## Success criteria

- A developer sets `daily_usd = 50.00` in `halyard.toml` and receives a
  warning in their Claude Code terminal when they start a session after
  crossing $50 that day.
- The warning is visible and clear — not buried in logs.
- Sessions proceed normally after the warning — no blocked work.
- `halyard budget` shows the current state in under 100ms.
- A project with no `[budget]` section behaves exactly as it does today.
- The budget check adds less than 100ms to the hook execution time.
