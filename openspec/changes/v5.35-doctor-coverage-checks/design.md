# v5.35 — Design

## The denominator is the whole design

The naive form of the coverage check — counted human time over total AI
session time — is worse than useless. Measured against a machine whose
timeclock had just been *corrected*:

```
all rows      907.6 h -> 9.3% coverage    (fires)
<=12h rows    105.5 h -> 79.9% coverage   (silent)
```

One 653-hour imported Codex rollout dominates the total. A check built on
it would fire loudest on healthy machines with long-lived imports, which is
precisely the population least in need of warning.

Excluding sessions past `_MAX_SESSION_SECONDS` reuses v5.33's bound and its
justification: a long-lived imported session is not evidence of continuous
human work. Sharing the constant means the check and the reconciliation
cannot drift to different definitions of a plausible session — if they did,
doctor could warn about a gap `repair --from-sessions` would then decline to
fill.

## Choosing 50%

Validated against the two real states of the same machine rather than
picked:

| state | coverage | verdict |
|---|---|---|
| pre-recovery (8.4 h) | 8% | fires |
| post-recovery (84.3 h) | 80% | silent |

An order of magnitude separates them, so the threshold is not delicately
placed. 50% is round, sits in the middle of a wide gap, and reads as an
honest "materially below" rather than a tuned constant.

The 1-hour AI floor exists so a new install cannot warn on day one: one
20-minute session and an empty timeclock is 0% coverage and means nothing.

## Reading the log rather than the filesystem

`capture.truncated` reads back the diagnostic log rather than re-stat'ing
every transcript. The log is the record of what actually happened; a
filesystem sweep would predict what *might* happen, cost more on every
doctor run, and after v5.34 raised the budget to 1 GiB it would almost
always predict nothing.

The parsing is deliberately loose — a substring match on the message this
codebase writes. If the message changes, the check goes quiet rather than
crashing, which is the right failure direction for an advisory signal.

## Both are warnings

Consistent with `unwired.*` and the ledger-duplicate canary. Neither
condition makes a report *wrong*: the sessions are recorded correctly, and a
truncated transcript still captured real work. They tell the user something
is missing, and the exit code stays a statement about correctness.

## What is not covered

Per-day and per-project coverage breakdown. The aggregate ratio answers the
question the check exists for — "is the auto-timer systematically losing
time?" — and a per-day view would fire on any legitimately quiet day.
