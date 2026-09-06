# v5.36 — The collapse discarded attribution, and its remedy did not exist

## Why

42% of the maintainer's captured tokens — 453.6M of 1.07B — reported as
belonging to no project. The tokens were attributed in the ledger; the read
path was throwing the attribution away.

### The collapse loses a project the rows agree on

`_canonical_gemini_row` picks one row per session group by rank:

```python
(s.input_tokens + s.output_tokens, 1 if s.project else 0, window, cache_read)
```

Tokens outrank attribution. So a later, larger, *unattributed* row wins over
earlier rows that carry a project — and the project is simply dropped.

Measured on the real ledger:

```
job codex:019fe77b  ->  75 rows, 74 carrying project=git/Nautilus
                        canonical row: no project, 15,217,312 in+out
                        best attributed row:        2,508,802 in+out
```

74 of 75 rows agree, and the collapse returns none of them. Two groups on
this machine were affected, together **371.1M tokens**.

The ranking answers "which row is most complete". That is a different
question from "what project was this". A row without a project is missing
information, not asserting absence — so the group's own answer should be
used when the winner has none.

Why the winner lacked one: re-importing after the v5.34 fix wrote a fresh
row from a directory with no git context. The largest row is often the
newest, and the newest is the one most likely to have been written outside
the project — so the ranking selects *against* attribution precisely when a
session has been re-imported.

### `halyard reattribute` never existed

`halyard adopt` prints:

> Existing hub sessions remain under `<old>` — run
> `halyard reattribute <old> <new>` to migrate them.

That command is referenced exactly once in the codebase: in the message
telling users to run it. It was never implemented.

This is the third instance of the same shape this track: v5.29's
`halyard hub <path>` (shadowed, unreachable) and v5.30's "the MCP SDK is not
installed" (advice that reproduced the error). A remedy nobody can run is
worse than no remedy, because it costs the user the attempt.

The consequence is visible: `git/Halyard` (25 sessions) and
`kormilo:halyard` (30 sessions) are the same project, split because
`link-repo` fixes attribution forward and nothing migrated the past.

## What

1. **Inherit attribution in the collapse.** When the canonical row has no
   project, take the group's — but only when the group agrees. Two rows
   naming different projects is stranger than a missing field, and guessing
   would move billable attribution onto a project the evidence does not
   support; unattributed is the honest answer there.
2. **Implement `halyard reattribute <source> <canonical>`.** Records a
   read-time alias via the existing `set_project_alias`, so history reports
   under one identity without the append-only ledger being rewritten.
   Dry-run by default and reports how many sessions move, because an alias
   silently shifts billable sessions between projects.
3. **`link-repo` now says so too.** It had the same fix-forward-only gap as
   `adopt` and did not mention it.

Verified on the real ledger: unattributed falls from 453.6M to 82.5M tokens,
and `reattribute git/Halyard kormilo:halyard` reports 25 sessions would move.

## Out of scope

- **Attributing imported sessions that carry no project at all.** The
  remaining 82.5M is mostly Codex and Copilot rollouts imported without git
  context. Inferring their project from timing overlap or a recorded cwd is
  a real feature with real false-positive risk, and belongs in its own
  change.
- Rewriting historical rows. The ledger is append-only by design; aliasing
  is the read-time equivalent and is reversible.
