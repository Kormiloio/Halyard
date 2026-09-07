# v5.41 — The money column was always zero

## Why

Every cost figure Halyard has ever shown this user is `$0.00`:

```
437 sessions in cache.db, 0 with cost_usd > 0
```

The dashboard's "At a glance" reads `$0.00`. The Models panel's Share
column is 0% for every row, because share is computed as a fraction of
total cost and the total is zero. Four separate panels are reporting a
confident number that is not a measurement.

Two independent causes, both of which turn *unpriced* into *free*.

### Cause 1 — the pricing table predates every model in use

```python
if model not in _merged_table:
    return 0.0                       # pricing.py:374-375
```

The bundled table holds 18 entries snapshotted 2026-05. The models
actually in the ledger:

| model | sessions | in+out | in table? |
|---|---:|---:|---|
| gpt-5.6-sol | 288 | 343.6M | no |
| claude-opus-5 | 97 | 1.76M | no |
| gpt-5.6-terra | 1 | 16.9M | no |
| claude-sonnet-5 | 1 | 3.3k | no |
| gemini-3.6-flash-high | 1 | 0 | no |

Not one is priced. `halyard update-pricing` does not help: the repo's own
`pricing/models.toml` is equally stale, so a refresh re-fetches the same
gap.

Worse, two entries that *are* present are **wrong** — they carry the
previous generation's rates:

| entry | table says | actual |
|---|---|---|
| `claude-opus-4-7` | $15 / $75 | **$5 / $25** |
| `claude-haiku-4-5` | $0.80 / $4.00 | **$1 / $5** |

So the table is not merely incomplete; where it does answer, it can be
wrong by 3x.

### Cause 2 — most collectors never price at all

`codex_app.py:295` hardcodes `cost_usd=0.0`. That is 292 sessions and
360.6M tokens — 82% of all token volume — unpriced regardless of the
table. The same hardcode appears in `cursor`, `copilot`, `windsurf`,
`vscode_otel`, and `antigravity`.

### The guard that existed and was never wired

`model_is_known()` is defined in `pricing.py` and used in exactly one
place: validating a model name read out of `settings.json`
(`claude_code.py:989`). It was never used to mark a session as unpriced.

## What

1. **Current rates**, sourced from vendor pricing pages and cited in
   `design.md`. Added to both the bundled `PRICING` dict (works offline)
   and `pricing/models.toml` (what `update-pricing` fetches).
2. **The two incorrect entries corrected.**
3. **Codex prices through `calculate_cost`** instead of hardcoding zero.
4. **Local models classified, not priced.** `_LOCAL_MODEL_MARKERS` moves
   out of `junie.py` into the shared collector module so an on-device
   MLX model is `billing="local"` everywhere — otherwise adding rates
   would start charging for on-device inference.
5. **Unpriced is no longer free.** A session whose model has no rate is
   reported as unpriced, surfaces render `n/a` rather than `$0.00`, and a
   doctor check names the offending models.
6. **Read-time repricing**, so the 437 sessions already on disk gain
   their cost without the append-only ledger being rewritten.

## Why read-time

Storing only the computed cost is what produced this bug: a stale table
baked `0.0` into 437 rows permanently. Repricing at read time means
adding a rate fixes history, exactly as v5.36's slug alias, v5.39's path
map, and v5.40's inheritance do for attribution. A row that already
carries a non-zero cost is never overwritten — the collector had better
information at the time than a table lookup does now.

## Not in scope

`db.py:564` hydrates `AiSession` from `cache.db` without
`tokens_available`, so it defaults to `True` and the `spend_tracked`
guard cannot fire on that path. Real, but the dashboard reads the ledger
via `parse_sessions`, so it is not what makes these panels wrong.
Recorded for its own change.
