# v5.32 — A 25 MB cap silently made large Codex sessions uncapturable

## Why

Found by acting on `halyard doctor`'s own advice and watching it fail.

Doctor reported the collector-drift canary firing:

```
WARNING codex (capture lagging) last captured 2026-09-02 14:03, but codex
        session files are as recent as 2026-09-05 09:00 (~3d uncaptured)
        fix: run `halyard import-codex`
```

Running the advised fix reported `No new Codex sessions to import.` The
canary and the importer disagreed, and the importer was wrong.

`_iter_jsonl_lines` capped reads at a **25 MB whole-file** limit and yielded
nothing above it; `_parse_session_file` then returned `None` and the caller
skipped the session — with no log line, no warning, and no doctor signal.
The two live rollouts on the maintainer's machine were 813 MB and 59 MB, so
both were permanently uncapturable. Re-running the importer could never
help, which is what made doctor's advice actively misleading.

Measured directly against the real file:

```
file size      : 852,120,599 bytes (813 MB)
cap            :  26,214,400 bytes (25 MB)
lines yielded  : 0
parse result   : None
```

The cap never did what it looks like it does. `_iter_jsonl_lines` is a
**streaming generator** — it yields line by line and never holds the file in
memory — so a whole-file size limit bounded nothing except how large a
session was allowed to be before it fell off a cliff. Memory is bounded by
the longest *line*, which the cap did not constrain at all.

The cost is concentrated exactly where it hurts most. Short sessions stay
under 25 MB and import fine; the long agentic runs that dominate token
totals blow past it and vanish. On this machine one session was recorded as
103,842,457 tokens when its rollout actually held **371,138,080** — a 3.6×
understatement, 267M tokens missing from a figure that had already been used
to reason about spend.

`gemini_history` hit this same wall and was already fixed for it, with a
comment that reads as a direct precedent:

> Generous so the importer can fully read a long session (one observed
> rollout was 825 MB of inline tool output)

Codex never got the same treatment.

## What

Adopt the shape `gemini_history` already uses:

- `_MAX_ROLLOUT_LINE_BYTES = 16 MiB` — per line, the bound that actually
  matches the streaming read and stops a pathological line. A single
  oversized line is skipped and parsing continues, rather than discarding
  the whole session.
- `_MAX_ROLLOUT_BYTES = 1 GiB` — total budget per parse, sized for real
  rollouts rather than an order of magnitude below them.
- **Truncation is now loud.** `_note_truncated` records to the diagnostic
  log when a rollout exceeds the budget. Losing data quietly is worse than
  losing it loudly; the silence is what let this run for weeks.

Symlink rejection is unchanged.

Verified end to end on the real 813 MB rollout: 0 lines yielded before,
13,338 after; the session parses; `halyard import-codex` imports 2 sessions
it had been refusing; the recorded Codex total moves from 148,225,877 to
419,845,235; and the drift canary stops firing.

## Out of scope

- **The same cap in the other collectors.** `claude_code.py:719`,
  `gemini_otel.py:25` (both 25 MB) and `antigravity.py:61` (50 MB) have the
  identical whole-file shape, and none of them warn on skip either. Only
  Codex is demonstrably losing data on this machine, and widening the change
  to every collector's untrusted-input handling at once is a much larger
  review. Recorded as follow-up.
- **A doctor check for oversized/skipped rollouts.** The diagnostic-log
  entry makes the loss discoverable; surfacing it as a first-class check is
  the better end state and belongs with the cross-collector pass.
- Re-deriving any spend or usage analysis from the corrected numbers. The
  ledger is now right; what was previously concluded from it is not, and
  that is a separate exercise.
