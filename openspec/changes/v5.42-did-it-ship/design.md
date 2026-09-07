# v5.42 — Design

## Why `--state all` rather than `--state merged`

The panel needs four outcomes — merged, open, closed-unmerged, and no PR —
so it has to see every state and classify from the payload it already
reads (`state`, `mergedAt`). Asking for merged only would fix the headline
and break the Open and Closed buckets.

`--limit 5` stays. `_best_pr_for_session` picks the candidate whose
`createdAt` is closest to the session end, which is exactly the
disambiguation a reused branch now needs — `--state all` is the first time
that function can receive more than one row in practice.

## Versioning the cache key

`cache_key = f"{remote or ''}:{branch}"` with a one-hour TTL. Entries
written before this change hold open-only results, so on any machine that
has run `outcome sync` in the last hour the fix would silently appear not
to work — the worst possible failure for a change whose whole point is
that a wrong answer looked like a real one.

The key becomes `f"{remote or ''}:{branch}:v2"`. A literal version marker
rather than the state string, so any future change to the query shape has
an obvious place to invalidate from.

## The denominator

```python
resolved = total - unsynced
pct = int((merged / resolved) * 100) if resolved else 0
```

`total` stays on the summary — the row counts and their percentages
describe the whole window, including how much of it is unresolved, which
is information the user needs. Only the *headline* changes denominator,
because the headline answers "of the work we could check, how much
shipped".

`measured` is a property (`resolved > 0`) rather than a stored field: it
is derivable, and a stored copy could disagree with the counts it is
derived from.

## Rendering an unmeasured panel

When `measured` is False the headline shows `—` and the caption reads that
nothing has been resolved yet, with the existing `halyard outcome sync`
hint already below it. Critically the panel takes **no** colour band in
that state: the bands are `leverage-low/mid/high`, and applying `low` to
an unmeasured panel is what made "not checked" look like "failed".

The hint text is unchanged and already correct. It was the only honest
element on the panel.

## What this does not fix

A session whose branch was deleted *and* whose PR was squashed under a
different head name is still unresolvable — `gh pr list --head` matches on
the branch name, and nothing in the ledger records the PR number. Out of
scope; recorded because "no PR" will remain slightly over-reported and
that should not be mistaken for this bug persisting.
