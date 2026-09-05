# Proposal: v5.26 — Auto-timer under-counts billable human time

## Why this exists

The auto-timer measures **how often you type**, not how long you work.
On a machine observed 2026-08-11 it recorded **34 minutes** for a day whose
own AI session log proves **2h 20m** of continuous session — a ~4×
under-count of billable hours, in the feature whose entire purpose is
billing accuracy.

This is not a misconfiguration. It is shipped behaviour, it is silent, and
it under-reports in the direction that costs the user money.

## The defect

The Stop hook *does* try to keep the clock fresh —
`claude_code.handle_stop_hook` calls `auto_timer_update_activity()`
(claude_code.py:612). But that function only refreshes a window that is
**already open**:

```python
state = _read_state()
if not state:
    return            # no open window → silently does nothing
```

Combine that with the idle policy, which closes a window **retroactively
at `last_activity`** rather than at the moment of closing, in two
independent places:

- `auto_timer.auto_timer_close_if_stale()` (standalone path)
- `hub_server._close_stale_presence()` → `_close_presence_now(now=last)`

The Hub's copy matters more than it looks: The Bridge polls presence, so
on a machine running the dashboard the window is closed *mid-turn*.

The failure sequence, as observed:

1. `16:12` prompt → window opens.
2. `16:31` turn ends → Stop refreshes `last_activity = 16:31`.
3. A single long turn runs `16:31 → 18:32`. No new prompt, so nothing
   refreshes anything.
4. `~17:01` the idle policy fires and writes `o 16:31:06`, clearing state.
5. `18:32` Stop fires → `auto_timer_update_activity()` finds no open
   window → **returns silently**. Two hours of work, already recorded as
   a session in the ledger, are unrecoverable from the timeclock.
6. `18:24` an unrelated prompt opens a fresh window.

So the clock effectively measures *prompt cadence*, capped at 30 minutes
per prompt. One prompt kicking off a two-hour agent run — the normal
shape of agentic work — is indistinguishable from walking away.

The Stop-hook refresh is not missing; it is **unable to reopen or
backfill**, which is precisely the case that matters.

### Observed evidence (2026-08-11)

Ledger:

```
16:12:24 → 16:31:06   claude-code
16:31:06 → 18:32:05   claude-code      ← 2h01m, one continuous session
```

Timeclock for the same day:

```
i 16:12:24 → o 16:31:06     18m
i 18:24:06 → (open)         ~17m
```

The stretch **16:31 → 18:24 is simply gone**, while Halyard's own session
log records work throughout it. The same day before repair had 12 dropped
opens; `halyard timeclock repair` recovered 2.2h → 3.5h, which is a
*second* symptom of the same root cause, not a separate bug.

## What changes

- **Turn completion counts as activity.** Every collector's stop hook
  refreshes the auto-timer, not just Claude Code's prompt-submit hook.
- **Session spans become the evidence of record.** On stop, ensure the
  timeclock covers the session's own `[start, end]`, merging with existing
  windows and never double-counting. A captured session row is proof that
  work happened; the timeclock should not contradict it.
- **Retroactive recovery.** `halyard timeclock repair` gains a mode that
  reconciles against `ai-sessions.log`, so days already lost can be
  recovered from evidence rather than written off.
- **Doctor check.** Warn when counted human time is materially below the
  AI session time for the same period — the signature of this defect.

## Success criteria

- A single prompt that starts a 2-hour agent run yields ~2 hours of
  counted human time, not 30 minutes.
- With The Bridge running and polling presence, the window is **not**
  closed mid-turn.
- Genuine idle is still excluded: closing an abandoned session after
  `INACTIVITY_MINUTES` past the **last evidence of work** is preserved.
- Reconciliation is idempotent, never double-counts an already-covered
  span, and never invents time beyond a recorded session's own bounds.
- `doctor` flags a day whose AI session time materially exceeds counted
  human time.

## Out of scope

- Changing `INACTIVITY_MINUTES`. Raising it would bill genuine idle time —
  the opposite failure, and worse for invoicing. The policy is not the
  bug; the missing evidence is.
- Human presence detection beyond captured AI activity (keyboard/IDE
  focus). Out of character for a local-first tool that captures metadata
  only.

## Risks and trade-offs

- **Over-counting unattended runs.** If an agent runs unattended for
  hours, session-span coverage now bills that time. That is the deliberate
  trade: the session *is* the work, and Halyard already records it as one
  session. Bounding coverage to the session's own start/end (never
  extending past it) keeps this defensible, and idle *between* sessions is
  still excluded.
- **Two writers.** The standalone path and the Hub both manage presence.
  Any fix must land in both or the Hub silently wins on machines running
  The Bridge — the exact reason this defect survives today.
- **Retroactive repair rewrites user time data.** It must stay dry-run by
  default, back up first, and show a diff — the contract
  `halyard timeclock repair` already honours.
