# v5.31 — Design

## Why reconcile instead of making the fallback idempotent

The smaller-looking fix is to relax `_start_timer_local`: if the active
timer it finds has the same slug we asked for, return it instead of
raising. Rejected, for two reasons.

It changes the meaning of a genuine error. `halyard start acme:auth` typed
twice by hand *should* say "already running" — that is useful information,
and the second invocation did not start anything. Making the local path
idempotent silences that everywhere, to fix a case that only arises after
a failed hub call.

It also cannot tell the two situations apart. A stale `~/.halyard/active`
left by a crashed run looks exactly like a timer the hub just committed.
Adopting both means a user who asks to start a timer can be silently
joined to an orphan from yesterday, with the elapsed clock already hours
in. The current wrong-but-loud error is better than that.

Scoping the new behaviour to the post-hub-attempt path keeps
`_start_timer_local` — and the `direct=True` path the hub itself uses —
completely unchanged.

## Why the hub's answer is the discriminator

The question being asked is precisely "did my write land?", and only the
hub can answer it. `read_state()` opens a **fresh** connection, so an
aborted response on the previous one does not prevent it; that is exactly
the failure being recovered from.

Requiring *both* the hub's report and the on-disk state to name our slug is
deliberate belt-and-braces. The hub's in-memory `state.project` and the
active file are written in the same handler but are separate pieces of
state; if they disagree, something stranger is happening than a dropped
response and the safe move is to decline to adopt and let the existing
local path raise.

When the hub is unreachable, `read_state()` returns `None` and we fall
through untouched. An unreachable hub cannot vouch for anything.

## Reporting the real elapsed time

The adopted `ActiveTimer` is built from `read_active_timer(prefer_hub=False)`
— the on-disk record — rather than synthesising `started=now,
elapsed_minutes=0`. If adoption ever fires on a timer older than the
current command (it should not, given the hub check, but the whole point
of this change is that "should not" is doing real work elsewhere), the
user sees the true age rather than a reset clock. A wrong start time is
harder to notice than a wrong error message, and it feeds billing.

## Testing a lost response without a flaky race

The bug needs the hub to commit and then fail to respond. Reproducing that
by actually racing a socket would reintroduce the flake this change exists
to remove.

Instead the tests drive the two halves deterministically:

- **The regression itself** — commit real state through the hub
  (`start_timer(..., direct=True)` against the fixture's project dir, plus
  the hub's in-memory state), then patch `hub_client.start_timer` to
  return `None` as a lost response does, and assert that `start_timer`
  returns the adopted timer instead of raising `TimerAlreadyRunning`.
- **The hub-is-down case** — same committed state, but `read_state` also
  returns `None`. Must still raise `TimerAlreadyRunning`: an unreachable
  hub vouches for nothing, and this is what protects a stale active file
  from being silently adopted.
- **Disagreement** — hub reports a different project than the on-disk
  slug. Must not adopt.
- **The elapsed-time contract** — an adopted timer reports the on-disk
  `started`, not a reset clock.

No threads, no sleeps, no sockets torn down mid-write; every path is
exercised by choosing what the two readers return.

## What this does not fix

`stop_timer` has the mirror-image race: the hub clears state, the response
is lost, `_try_stop_timer_via_hub` returns `None`, and the local fallback
reports `was_running=False` — telling the user nothing was running when
their command did in fact stop the timer. Less harmful (the desired end
state was reached, only the report is wrong) but the same shape. Left for
a follow-up so this change stays reviewable; recorded in `tasks.md`.
