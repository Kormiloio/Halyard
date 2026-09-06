# v5.40 — Design

## Inheritance is a property of the field kind, not of one field

The bug is small; the reason it happened is the interesting part. v5.36
wrote the right rule and bound it to one field name:

```python
if winner.project:
    return winner
inherited = _inherited_project(rows)
```

Nothing in that shape says *why* `project` is inherited, so when
`source_path` arrived three changes later there was no pressure to ask
whether it needed the same treatment. The generalised form states the
rule once:

```python
project     = winner.project     or _agreed(rows, "project")
source_path = winner.source_path or _agreed(rows, "source_path")
```

Both fields share the property that makes inheritance correct: **a row
without one is missing information, not asserting absence.** Token counts
are the opposite — a row with fewer tokens is making a claim about that
row — which is why they are ranked, not inherited. Any future field
should be classified against that distinction before it is added here.

## Why `_agreed` takes a string attribute

`getattr` by name rather than a callable or a typed accessor, because the
two call sites want the field's *name* in the message and because a
callable would have to be defined per field, reintroducing the
per-field-ness the change removes. The `str()` around the popped value is
for mypy: `getattr` widens to `Any`, and the function's contract is
`str | None`.

## Why not `replace(winner, **updates)`

The obvious compression is to build a dict of changed fields and splat it:

```python
updates = {k: v for k, v in (...) if v != getattr(winner, k)}
return replace(winner, **updates) if updates else winner
```

mypy cannot type-check a dict splat against a dataclass constructor — the
keys are `str`, so every field becomes unchecked. Explicit keyword
arguments cost two lines and keep a typo in a field name a type error
rather than a `TypeError` at read time on a user's ledger. The early
return when nothing changed is kept so the common case still returns the
identical object rather than a copy.

## Why not fix this in the importer instead

The re-imported row *did* carry the path; the importer is doing its job.
The loss happens at read time, in the collapse. Fixing it there means it
also repairs ledgers already written — the same read-time-resolution
principle as v5.36's slug aliases, v5.39's path map, and v5.33's timeclock
reconciliation. The append-only ledger is never rewritten.

## Limits

A group whose rows name two different paths still resolves to none. That
is deliberate and matches `project`: if one job group disagrees about
where it ran, something stranger than a missing field is happening, and
the honest report is "unattributed" rather than a coin flip that moves
billable tokens.
