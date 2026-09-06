# v5.35 — Doctor checks for the two silent losses

## Why

Both defects this track uncovered were silent, and both were found the same
way: a human noticed Halyard's own signals disagreeing. Neither had a check.

- **v5.26** — counted human time was ~4x below the work the session ledger
  recorded. Nothing flagged it; it surfaced only because a day's timeclock
  looked implausible next to the same day's sessions.
- **v5.32 / v5.34** — transcripts past a size cap were skipped entirely. The
  fix made truncation *loud* by writing to the diagnostic log, but a log
  nobody opens is barely louder than silence.

Both were deferred from their own changesets for the same stated reason: the
threshold had to be tuned against real data first, because a check that
cries wolf is worse than no check. That data now exists.

## The tuning result, which decided the design

Measured against the maintainer's machine, whose timeclock is now *correct*:

```
counted human time            :  84.3 h
AI session time (all rows)    : 907.6 h   ratio   9.3%
AI session time (<=12h rows)  : 105.5 h   ratio  79.9%
```

Counted naively, a healthy machine reads **9%** and the check fires. The
653-hour imported Codex rollout swamps the denominator.

So the denominator excludes sessions longer than `_MAX_SESSION_SECONDS` —
the same bound v5.33's reconciliation uses, and for the same reason: a
long-lived imported session is not evidence of continuous work. With it,
the healthy machine reads **80%** and stays silent.

Validated in both directions against real files: replaying the pre-recovery
timeclock (8.4 h) fires at **8%**; the post-recovery state is silent. A 50%
threshold separates them with wide margin on both sides.

## What

- **`timeclock.coverage`** — warn when counted human time is below 50% of
  bounded AI session time, gated on at least 1 hour of AI evidence so a new
  install or a short day cannot trip it. Fix text points at
  `halyard timeclock repair --from-sessions`.
- **`capture.truncated`** — surface truncation events already recorded in
  the diagnostic log, naming the files.

Both `warning`, never `error`: reports remain correct and usable, and these
are advisory. Consistent with the `unwired.*` and ledger-duplicate checks.

## Out of scope

- Re-stat'ing every transcript on each doctor run to predict truncation
  before it happens. The log is the record of what actually occurred; a
  filesystem sweep costs more than the signal is worth, and after v5.34 the
  budget is 1 GiB, so truncation is rare by construction.
- Per-day or per-project coverage breakdown. The aggregate ratio is what
  distinguishes "the auto-timer is broken" from "a quiet week", which is the
  question this check exists to answer.
