# v5.41 — Design

## Rate sources

Every rate below was read from the vendor's own pricing page on
2026-09-06. USD per million tokens.

**Anthropic** — <https://platform.claude.com/docs/en/about-claude/pricing>

| model | input | output | cache read | cache write (5m) |
|---|---:|---:|---:|---:|
| claude-opus-5 | 5.00 | 25.00 | 0.50 (0.10x) | 6.25 (1.25x) |
| claude-sonnet-5 | 2.00 | 10.00 | 0.20 (0.10x) | 2.50 (1.25x) |
| claude-opus-4-7 | 5.00 | 25.00 | 0.50 | 6.25 |
| claude-haiku-4-5 | 1.00 | 5.00 | 0.10 | 1.25 |

The last two are **corrections**. The table carried `$15/$75` for
Opus 4.7 (that is Opus 4.1's rate) and `$0.80/$4.00` for Haiku 4.5 (that
is Haiku 3.5's). Both were overstating or understating real cost, which
is worse than a missing entry because it looks authoritative.

**OpenAI** — <https://developers.openai.com/api/docs/pricing>

| model | input | cached input | output |
|---|---:|---:|---:|
| gpt-5.6-sol | 4.00 | 0.40 (0.10x) | 20.00 |
| gpt-5.6-terra | 2.00 | 0.20 (0.10x) | 12.00 |

**Google** — <https://ai.google.dev/gemini-api/docs/pricing>

| model | input | output | context cache |
|---|---:|---:|---:|
| gemini-3.6-flash | 0.75 | 3.75 | 0.075 (0.10x) |

Gemini's published rate doubles on 2027-01-01. The table records today's
rate; `update-pricing` is the mechanism for the change, not a hardcoded
future date.

## Why the multiplier floor moves from `0 <` to `0 <=`

OpenAI charges nothing for cache *writes* — there is no write fee, only a
discounted read. The current validator rejects zero:

```python
if not isinstance(val, (int, float)) or not (0 < float(val) <= _MAX_MULTIPLIER):
```

so "free" is inexpressible and silently falls back to `1.25`, inventing a
charge. Zero is a legitimate multiplier; negative is not. The bound
becomes `0 <= float(val)`.

This has no effect on today's numbers — every OpenAI row in the ledger
has `cache_write == 0` — but the schema should be able to state the
truth before a row appears that depends on it.

## Local models are classified, not priced

`_LOCAL_MODEL_MARKERS` currently lives in `junie.py` and is applied by
that collector alone. Two `claude-code` sessions on `muse-glimmer:30b-mlx`
— 2.95M tokens of on-device inference — are recorded `billing="api"`.

This has to be fixed *in the same change* as the rates, not after. Adding
prices without it would not leave those sessions at zero; it would start
charging API rates for compute that ran on the user's own laptop. The
markers move to `collectors/__init__.py` and every collector applies them.

A local session is `billing="local"`, cost `0.0`, and — importantly — is
**not** flagged unpriced. Its zero is a measurement, not a gap.

## Unpriced vs. free

The distinction is derived, not stored:

```python
def cost_is_known(model, billing) -> bool:
    return billing == "local" or model_is_known(model)
```

Derived rather than written to the ledger because pricing coverage is a
property of *the table*, which changes. A session recorded today against
an unpriced model should become priced the moment a rate is added — the
same reason attribution resolves at read time. Writing a
`cost_known=false` field would freeze a fact about the table into a row
about a session.

## Read-time repricing

`resolve_costs(sessions)` runs inside `parse_sessions`, beside
`resolve_paths`. For each row:

- `cost_usd != 0.0` → untouched. The collector had direct evidence
  (Junie and Claude Code report vendor-computed cost); a table lookup now
  is weaker evidence than a number the tool gave us then.
- `billing == "local"` → untouched at `0.0`.
- model unpriced → left `0.0`, flagged unpriced for the surfaces.
- otherwise → `calculate_cost(model, in, out, cache_read, cache_write)`.

Order matters relative to the v5.40 collapse: repricing runs **after**
`collapse_gemini_sessions`, because the canonical row is the one whose
tokens are correct, and pricing a row that is about to be discarded is
wasted work that could also disagree with the survivor.

The ledger is never rewritten. Re-running with a corrected table yields
corrected history on the next read.

## What this does to the user's numbers

Repricing 437 sessions at these rates turns `$0.00` into a real figure
dominated by `gpt-5.6-sol`: 307M input, 36.6M output, and 12.68 **billion**
cache-read tokens at $0.40/MTok. The cache-read line alone is the largest
single term. That is the honest number, and it is the first time the
"is this spend worth it" question has had a denominator.

## Amendments made during implementation

**Codex is not priced in the collector.** The plan said `codex_app` would
call `calculate_cost` in place of its hardcoded zero. It does not, and
should not: Codex reports no cost of its own, so the collector has no
evidence a read-time table lookup lacks. Writing a figure at import would
freeze the rate into the row — which is precisely how a stale table baked
`0.0` into 437 rows. `cost_usd=0.0` now means "the tool reported nothing"
and `resolve_costs` supplies the number, so a later rate correction
reaches history. One mechanism, not two.

**`cost_is_known` checks the model name, not only stored `billing`.**
Billing class is written at capture time. The two `muse-glimmer:30b-mlx`
sessions already on disk say `billing="api"` because the collector did not
yet classify local models, and re-importing a finished session is not
always possible. Checking `model_is_local(model)` as well means those rows
read as *known-free* rather than *unpriced* without a rewrite — the same
read-time principle as the rest of this change. Without it the fix would
have been half-applied: new local sessions correct, old ones mislabelled
`n/a`.

## A dotted TOML key is a silent unpricing

Model names contain dots. Written bare, `[models.gpt-5.6-sol]` parses as
nested tables — `models` → `gpt-5` → `6-sol` — so the model is absent
from the table with no error anywhere, and `calculate_cost` returns 0.0
exactly as if no rate had been written. The keys must be quoted:
`[models."gpt-5.6-sol"]`.

The guard test written for this found the same bug **already shipped**:
`gemini-2.5-pro` and `gemini-2.5-flash` were bare-dotted in
`pricing/models.toml`, so neither has ever existed as a key in the remote
table. They were priced only by the bundled dict, and any user who ran
`update-pricing` had them silently unpriced. Both are now quoted.

This is the same failure mode as the rest of the change — a rate that is
missing is indistinguishable from a rate of zero — arriving through the
data format rather than the code.

## Limits

- Codex is billed through a ChatGPT subscription, not metered per token.
  Pricing it at API list rates answers "what did this consume at market
  rate", not "what was I charged". Surfaces must label it imputed. The
  user chose this basis explicitly over amortizing the seat cost.
- `gpt-oss-120b-medium`, `composer-2.5-fast`, `codex-auto-review`, and
  `antigravity-unknown` remain unpriced. They carry no tokens today, and
  inventing a rate for a model whose hosting is unknown is the failure
  this change exists to stop.
