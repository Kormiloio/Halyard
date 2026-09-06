# v5.36 — Design

## Inherit, do not re-rank

The tempting fix is to move `has_project` above tokens in the rank tuple.
Rejected: that trades one loss for another. The attributed row is often the
*earlier, smaller* snapshot of a growing session, so preferring it would
discard the token completeness the ranking exists to secure — swapping a
wrong project for wrong totals.

The two questions are independent. "Which row is most complete" is answered
by tokens; "what project was this" is answered by any row that knows. So the
ranking is untouched and attribution is inherited afterwards.

## Why agreement is required

`_inherited_project` returns a project only when the group names exactly
one. A group naming two is not a missing field — it is a contradiction, and
resolving it by majority or recency would move billable tokens onto a
project the evidence does not support.

Leaving it unattributed is visible and recoverable: the user sees the gap
and can alias it. Silently picking one is neither.

## Why aliasing rather than rewriting

`reattribute` records a read-time alias through the existing
`set_project_alias`/`canonical_project` machinery from v5.8 rather than
editing the ledger.

The ledger is append-only by contract, and rewriting it to fix a slug would
break that for a cosmetic gain. Aliasing is also reversible — deleting the
entry restores the previous view — where a rewrite is not. `canonical_project`
already follows alias chains with a cycle guard, so `A → B → C` collapses to
one bucket.

Dry-run is the default because an alias silently moves billable sessions
between projects. It reports the affected count so the decision is informed,
matching the contract `timeclock repair` established.

## The recurring shape, again

Three commands in this track were advertised and absent or unreachable:
`halyard hub <path>` (v5.29), the MCP reinstall advice (v5.30), and
`halyard reattribute` here. All three shared a property: the message was
written alongside the feature it described, and nothing tied the two
together, so the feature could be dropped or renamed without the message
noticing.

`test_reattribute_exists` is a thin guard against exactly that — it asserts
only that the command resolves, which is the property that was missing.

## Testing

The collapse tests are unit-level over constructed rows, because the
interesting cases are combinations the real ledger happens not to contain:
a group that disagrees, a group with no project anywhere, unrelated jobs
that must not merge. The observed 74-of-75 case is pinned as its own test
with the real token values.

The CLI tests cover the safety contract — dry run writes nothing, apply
records the alias, the ledger is byte-identical afterwards — mirroring the
v5.33 repair tests.
