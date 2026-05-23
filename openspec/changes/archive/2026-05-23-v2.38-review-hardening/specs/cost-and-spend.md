# Spec — Cost computation and spend totals

## Requirement: Deterministic cost rounding

WHEN `calculate_cost()` computes a session cost from token counts and rates
THEN the computation MUST use `decimal.Decimal` internally
AND the returned value MUST be quantized to 4 decimal places using
`ROUND_HALF_UP`
AND the same inputs MUST always produce the same output regardless of
accumulation order.

WHEN an invoice or voyage monetary amount is rounded
THEN it MUST be quantized to 2 decimal places using `ROUND_HALF_UP`
(not Python's banker's `round()`).

## Requirement: Single spend-summing convention

WHEN `halyard budget` or invoicing sums session spend for a period
THEN it MUST call the shared `usage.sum_spend()` helper
AND the period window MUST be half-open on session end:
`period_start <= session.end < period_end`.

The ledger keeps its per-project bucketed accumulation (it partitions by
plan and tracks inferred flags), but MUST round monetary values with the
same `Decimal` / `ROUND_HALF_UP` convention.

WHEN `api_only` is requested
THEN only sessions with `billing == "api"` and a positive cost contribute.

## Requirement: Pricing fallback is never silent

WHEN the local `pricing.toml` cannot be read for any reason — decode error,
value error, OR `OSError`
THEN a single actionable warning MUST be written to stderr naming the file
and the consequence (falling back to bundled prices).

## Requirement: Pricing multipliers are bounded

WHEN a pricing multiplier is loaded from a remote table OR the local file
THEN a value `<= 0` MUST be rejected
AND a value `> 10` MUST be rejected
so a malformed multiplier cannot silently inflate cost.

## Requirement: Pricing cache invalidates atomically

WHEN `update_pricing()` refreshes the pricing table
THEN both base rates and multipliers MUST be invalidated together
so a single process run never mixes old rates with new multipliers.
