# v5.17 — Design

## B14 — db CSV double-serialization

`AiSession.mcp_server_names` is typed `str | None` and already holds the
sorted, allowlisted CSV (built once at write time). `",".join(<str>)` treats
the string as an iterable of characters. The fix writes the value through
unchanged (`session.mcp_server_names or ""`); the `None`→`""` change is inert
because the only reader (`leverage.summarize_mcp` via `(x or "").split(",")`)
and `get_recent_branch_activity` treat `""` and SQL `NULL` identically.

## B15 — zero rate is a real rate

`x or y` collapses every falsy `x`, but `0.0` is a meaningful billing rate
(comp / pro-bono / waived). Replace the `or` chain with explicit
`a if a is not None else (b if b is not None else c)` so only a genuinely
absent (`None`) override falls through to the next source.

## B16 — period source must match selection source

Sessions are selected into an invoice by their `end` (a session is billed in
the period it *completed*). The appendix must therefore derive its ledger
month from the same period window, not from `min(s.start)` — otherwise a
session that started in the previous month but ended in this one drags the
whole appendix ledger (and `AiPlan.is_active_in`, and the period label) back
to the wrong month. Pass the invoice `period_start`/`period_end` (or the
derived ledger year/month) through to the appendix.

## B17 — one billing convention, everywhere

The breakdowns are the source of truth and use `sum_spend(api_only=True)`
(Decimal-quantized, drops non-`api`/credits/zero-cost). The headline must use
the *same* function so "captured spend" always equals the sum of the bars.
Likewise `_model_buckets` must apply one billing filter to both its
single-model and multi-model branches so a subscription session is either
counted in both or neither — never `$0` in one view and a calculated cost in
the other.

This is a deliberate behavior change: the headline now excludes
credit/subscription cost (matching the bars), and multi-model subscription
sessions now show `$0` like their single-model counterparts. A search of the
test suite found no existing assertion encoding the old (inconsistent)
numbers, so no existing test needed updating — but the change is real and is
recorded here.

## Testing

Each fix gets a focused regression test: a multi-server CSV round-trip
(B14), a `0.0`-rate invoice (B15), a month-straddling session (B16), and a
mixed-billing session set whose headline must equal the bar sum (B17).
