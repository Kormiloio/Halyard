# v5.42 — "Did it ship?" could not answer yes

## Why

The Leverage panel asks whether AI sessions land in merged PRs. On a
machine that had merged four PRs that same afternoon it read:

```
0%    0 of 140 sessions landed in merged PRs
      Not synced   140   100%
```

Two defects, and the second one hides the first.

### 1. The resolver can only see open PRs

```python
cmd = ["gh", "pr", "list", "--head", branch, "--json", ...]
```

No `--state`. `gh pr list` defaults to **open**. A merged PR — the exact
thing the panel is asking about — is invisible to it. Demonstrated
against a branch this repo merged as PR #38:

```
$ gh pr list --head fix/v5.40-inherit-source-path --json number,state
[]

$ gh pr list --head fix/v5.40-inherit-source-path --state all --json number,state
[{"number":38,"state":"MERGED","mergedAt":"2026-09-06T17:04:27Z"}]
```

So `halyard outcome sync` resolves every session to "no PR" and writes
that as a fact. On the machine in question a dry run produced **92 of 92
sessions → none**, every one of them wrong for any session whose branch
had been merged.

The feature could never report success. It asked a question it had made
unanswerable.

### 2. Unmeasured renders as a failing score

```python
pct = int((merged / total) * 100) if total else 0     # leverage.py:66
```

`total` counts every session in the window, including the ones never
resolved. With 140 unsynced sessions the panel computes `0 / 140` and
displays a grey `0%` — and `dashboard.py:1851` picks its colour band from
that same number, so an unmeasured panel is styled `leverage-low`, i.e.
as a bad result.

"Nothing shipped" and "nobody looked" render identically. This is the
defect class v5.29, v5.30, v5.31, v5.35 and v5.41 each fixed in their own
corner: a missing measurement collapsing into a confident zero.

The panel's own struggle line already gets this right — it discloses
"over 132 of 140 sessions; rest: not captured", and the comment at
`dashboard.py:1894` says rejections are "never a bare 0". The rule was
known and applied to the secondary line, not the headline.

## What

- **`--state all`** on the PR lookup, so a merged PR is findable.
- **The cache key is versioned.** `pr_cache` holds open-only results under
  `{remote}:{branch}` with a 1-hour TTL; without a new key the fix would
  appear not to work for an hour.
- **The share is computed over resolved sessions only** —
  `merged / (total - unsynced)`.
- **When nothing is resolved the panel says so** rather than showing a
  percentage, and takes no colour band.

## Note on ordering

The denominator was the reported symptom, but fixing it alone would have
turned a false `0%` into a *differently* false one: with `--state all`
missing, every session resolves to a real-looking `none`, the denominator
becomes non-zero, and the panel confidently reports 0% shipped. Running
`outcome sync` before the resolver fix would also have written 92 wrong
records that a later run would need `--force` to correct.
