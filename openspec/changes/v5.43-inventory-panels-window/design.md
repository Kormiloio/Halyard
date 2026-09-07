# v5.43 — Design

## Which panels lose the window, and why that line

The split is **inventory vs. period**:

| panel | window | why |
|---|---|---|
| Voyage Roster | none | a project is not a monthly fact; a voyage spans months |
| Models (Mix) | none | which models you use is an inventory question |
| Tools (Capture) | none | same, and leaving it month-scoped beside an all-time Models table would be worse than either choice alone |
| Spend / Costs | month | an invoice covers a month |
| Outcomes | 30d rolling | already its own window (`LEVERAGE_WINDOW_DAYS`) |
| At a glance | month | period summary; unchanged here |

Tools was not named in the request, only "Roster + Mix". It is included
because it is the same class of panel and the alternative is an
inconsistency the user would have to hold in their head: Models showing
all time and Tools showing September, side by side, with no label
distinguishing them.

`state.all_sessions` already exists and is already used this way by the
Leverage panel and the usage analytics, so this is plumbing that is
present, not new.

## Why input+output, not total tokens

Cache reads are **96.7%** of this user's token volume — 1.44 billion of
1.49 billion. That number is a function of conversation length and the
tool's caching strategy, not of work performed, and it is priced at a
tenth of input. Ranking by it inverts the answer:

```
by in+out :  codex 78.2%  >  claude-code 18.2%
by total  :  claude-code 67.0%  >  codex 31.5%
```

Those cannot both be "the mix". The one that reflects work done is
in+out, and the user confirmed that reading when the discrepancy was
shown to them.

## `CostBucket.work_tokens`

`_bucket_costs` already groups the sessions it needs; it gains a summed
`work_tokens` (input + output). A new field on the existing bucket rather
than switching the panel to `ModelUsageBucket`, because `CostBucket` is
what `by_project`/`by_model`/`by_tool` all produce and the project and
tool tables would otherwise diverge from the model one for no reason.

Default `0` so the three other construction sites and any test building a
bucket by hand keep working.

## The share denominator excludes nothing

Unlike cost share, every session has a token count, so no row is dropped
from the denominator. A model with zero tokens (Antigravity reports none)
renders `0%` — which is correct and not a gap: it genuinely did no
measurable token work. That is different from the `n/a` case v5.41
introduced for *cost*, where the number is unknown rather than zero, and
the two must not be conflated.

## The cost cell grew a fourth state, and why that was not scope creep

Adding the Tokens column immediately put `17.4M` next to `$0.00` for
Codex. `sum_spend` counts only `billing == "api"`, so a credits-billed
bucket sums to zero — accurate as *API* spend, and read beside 17.4M
tokens it says "this was free". That is the identical misreading this
panel already produced twice, surfaced by the change rather than
introduced by it, so it is fixed here.

The cell now has four states, and only one is a number:

| state | shows | means |
|---|---|---|
| API-billed, priced | `$732.78` | real dollars |
| unpriced (v5.41) | `n/a` | no published rate; spend unknown |
| credits | `credits` | real spend, not API spend |
| local | `$0.00` | on-device; the zero is a measurement |

`local` is deliberately a separate flag from `not api_billed`. The first
version reused `api_billed` and labelled `Qwen3.6-27B-MLX-4bit` as
"billed to a subscription", which is false — v5.41 established that a
local zero is a measurement, and that distinction has to survive here.

## Caveat on cross-tool token comparison

in+out is comparable across these tools only because `codex_app` runs
`normalise_input(..., cache_inclusive=True)` to net cached input out of
Codex's gross figure. Without that the two would be counting different
things and no share over them would mean anything. Any new collector
reporting gross input must do the same or this panel silently misranks.

## What the user will see

`kormilo:mycelium` appears on the roster with 1 session. The Models table
ranks `gpt-5.6-sol` first by work done rather than showing four zeros.
