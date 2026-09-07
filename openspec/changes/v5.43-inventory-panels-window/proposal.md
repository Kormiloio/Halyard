# v5.43 — Inventory panels showed a calendar month and called it everything

## Why

The user asked three times why the Mycelium project was missing from the
dashboard. v5.39 gave it a recorded path, v5.40 made that path survive the
collapse, and `link-path` attributed it. Verified in the ledger:

```
kormilo:mycelium   1 session
```

It still did not appear. The cause is unrelated to attribution:

```python
if not all_time:
    period_label = clock.strftime("%B %Y")
    sessions = [s for s in sessions
                if s.start.year == clock.year and s.start.month == clock.month]
```

The dashboard report is scoped to the **current calendar month**. Today is
2026-09-06; the Mycelium session is 2026-08-27. Ten days ago, and gone.

```
all sessions: 115   in September: 97   dropped: 18

kormilo:halyard    all=98  september=92
git/Nautilus       all= 2  september= 1   <- survives on one 09-05 session
kormilo:mycelium   all= 1  september= 0   <- invisible
```

A window is fine for money — a month is what an invoice covers. It is
wrong for **inventory**: which projects exist, which models you use. Those
are not monthly facts. On the 1st of a month the Voyage Roster is empty
and every project the user has ever worked on has apparently vanished.

## The second defect, in the same panel family

The Models table's Share column is a fraction of **cost**:

```python
total_cost = sum(b.cost_usd for b in bucket_list if b.priced)
pct = int((bucket.cost_usd / total_cost) * 100)
```

Before v5.41 every cost was `$0.00`, so every row read `0%` — a column of
zeros presented as a measurement. v5.41 made costs real, so it now
produces numbers, but cost is still the wrong denominator for a panel
titled **Mix**: it answers "where did the money go", not "what do you
use", and it drops local and unpriced models out of the comparison
entirely.

The sibling Tools table has always used a share that works without cost
data (`sessions / total_sessions`), which is why it rendered 66% / 29% /
1% / 1% while Models showed four zeros. Same file, ~25 lines apart.

## What

- **Roster and the Mix/Capture tables read `all_sessions`**, not the
  month-scoped report. Spend and outcome panels keep their window: those
  genuinely are period questions.
- **Models Share becomes input+output token share**, with a Tokens column
  so the figure is legible — the same column set the Tools table already
  has.

Input+output rather than total tokens because cache reads are 96.7% of
this user's token volume and are a property of the tool's caching policy,
not of work done. Ranking by total reverses which tool dominates
(claude-code 67% by total, codex 78% by in+out).

## Not in scope

The "At a glance" strip still reports total tokens including cache, and
still labels a month-scoped spend without naming the period. Recorded
separately — this change is about the inventory panels.
