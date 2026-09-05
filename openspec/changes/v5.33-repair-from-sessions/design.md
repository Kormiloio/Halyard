# v5.33 — Design

## Why skip rather than clamp

A session longer than `_MAX_SESSION_SECONDS` could be clamped to its first
12 hours instead of dropped. Rejected: that assumes the work happened at the
start of the span, which is a guess dressed as data. For the 653-hour
rollout the true answer is "this row says nothing about when a human was
present", and the honest response is to claim nothing from it and say so.

Returning `skipped_minutes` matters for the same reason. Silently excluding
89% of the ledger would be its own kind of wrong — the user should see that
a bound was applied and how much it removed, so they can judge it.

## Why `_MAX_SESSION_SECONDS` and not a new threshold

The codebase already encodes the judgement "a single session longer than
this is not plausible" at `collectors/__init__.py:17`, and the live
collectors enforce it. Reusing it means the reconciler and the collectors
cannot drift to different definitions of a plausible session, and there is
no second number to tune.

It also lands correctly on the boundary: sessions capped at exactly 12 h by
the collectors are `== _MAX_SESSION_SECONDS`, and the check is `>`, so
legitimately-capped rows still count. A test pins that boundary.

## Open entries prove nothing

`_windows_from_lines` ignores an unclosed `i` rather than treating it as
covering "until now". A forgotten clock-in would otherwise suppress every
recovery after it — one stale line silently disabling the feature. An open
entry has no end; it cannot establish coverage of any particular span.

## Sharing the write path

`_emit` factors the diff/backup/write out of the original repair so both
modes go through it. The safety contract — dry-run by default, timestamped
backup before any write, atomic replace — is the part that must not drift
between two modes that both rewrite user time data.

## Testing

The dangerous failure is double-billing, so most tests assert what must
*not* be proposed: overlapping sessions bill once, identical sessions bill
once, a covered span proposes nothing, re-running proposes nothing, idle
between sessions is never claimed, history is appended never rewritten.

The plausibility bound has its own three: an implausibly long session is
skipped entirely, a session at exactly the cap still counts, and one skipped
row does not suppress the legitimate ones alongside it.

The CLI tests cover the safety contract directly — dry run leaves the file
byte-identical, `--apply` writes a backup whose contents match the original.
