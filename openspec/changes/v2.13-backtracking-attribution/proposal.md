# Proposal: v2.13 — Backtracking Attribution

## Why

AI sessions captured by hooks carry no project context at write time. Today a
user must run `halyard assign` to manually attribute them. In practice, users
often forget, and sessions accumulate as unattributed noise.

However, Halyard already knows *when* the user was working on a project — the
timeclock records exact start/stop windows per project. A session whose
timestamp falls inside a timer window almost certainly belongs to that project.
We can use this to attribute sessions automatically, without prompting.

## What changes

### Auto-attribution on `halyard stop`

When `halyard stop` is called, scan `ai-sessions.log` for unattributed sessions
whose start time falls within the timer window that just closed. Attribute them
to the stopped project automatically.

Print a summary: `Attributed 3 AI session(s) to acme:auth-migration.`

If zero sessions fall in the window, print nothing.

### `halyard backfill` command

A standalone command that walks all closed timeclock windows in
`time.timeclock` and attributes any unattributed AI sessions that fall within
each window.

Useful for users who already have historical data and want to clean up in bulk.

Options:
- `--dry-run` — show what would be attributed without writing.
- `--confirm` — interactive mode; prompt before each attribution (default for
  ambiguous overlapping windows).
- `--project <slug>` — restrict to a single project.

### Overlap handling

If a session's time window overlaps multiple timeclock entries for different
projects, it is treated as ambiguous. Ambiguous sessions are skipped in
automatic mode and surfaced in interactive/confirm mode.

## What stays the same

- `halyard assign` remains available for manual attribution.
- `halyard confirm-attribution` remains for interactive review.
- Sessions are never modified destructively; attribution is written as a new
  `project=` key on the existing log line.
- Unattributed sessions that have no matching timeclock window remain
  unattributed.

## Out of scope

- Real-time attribution (attributing sessions while a timer is running).
- Attribution based on git branch or directory inference.
- Cross-project session splitting.

## Success criteria

- `halyard stop` attributes sessions from the closed window and prints a count.
- `halyard backfill --dry-run` lists sessions that would be attributed with
  their inferred project, without writing.
- `halyard backfill` attributes all unambiguous sessions.
- Zero regressions in existing attribution tests.
