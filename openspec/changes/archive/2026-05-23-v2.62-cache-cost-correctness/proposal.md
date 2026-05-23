# v2.62 — Cache-Aware Cost Correctness

## Problem

`pricing.calculate_cost` already prices cache correctly in principle:
cache reads at `_CACHE_READ_MULTIPLIER` (0.10× input) and writes at
`_CACHE_WRITE_MULTIPLIER` (1.25× input), both per-model overridable.
The risk is **upstream of pricing — in what the collectors capture**:

1. **Cache writes uncaptured for Gemini/Codex.** Only `claude_code`
   and `cursor` set `cache_write`; `gemini_cli` and `codex_app` set
   `cache_read` only. Cache *creation* is the most expensive token
   class (1.25×) — silently dropping it under-states cost.
2. **Possible input double-count.** Gemini's own summary showed
   `Input Tokens 1,022,341` alongside `Cache Reads 838,991`. If a
   tool reports `input_tokens` *inclusive* of cached tokens and
   Halyard also bills `cache_read` separately, the same tokens are
   charged twice (once at 1.0×, once at 0.10×). If `input_tokens` is
   *exclusive*, today's math is correct. **This is unknown per
   collector and unverified.** For a tool whose moat is a trustworthy
   dollar figure, an unverified double-count is the worst kind of
   defect.

This is a cost-correctness audit, the same trust thread as
v2.53–v2.61.

## Goal

Establish and enforce a single, documented token contract per
collector, and capture the full cache picture.

- **Audit** each collector (Claude, Cursor, Gemini, Codex): does its
  reported `input_tokens` include or exclude `cache_read`/
  `cache_write`? Document the answer per collector, sourced from the
  tool's payload/transcript semantics, not assumed.
- **Normalise** to one invariant: `input_tokens` is **fresh
  (non-cached) input only**; cached tokens live solely in
  `cache_read`/`cache_write`. Any collector that currently emits
  cache-inclusive input is corrected at capture.
- **Capture `cache_write`** for Gemini and Codex where the
  payload/transcript exposes it (`None` if it genuinely doesn't —
  unavailable is not zero).
- **Regression-proof** the invariant with a cost test per collector
  against a known fixture.

## Constraints honored

- **No pricing-table change.** Multipliers and per-model overrides are
  already right; this fixes capture, not rates.
- **Unavailable is not zero.** A collector with no cache-write signal
  keeps `cache_write=None`; cost simply omits that term.
- **Trust labels unchanged.** Still "captured" when tokens are real.
- **Backward compatible.** Historical lines are not rewritten; the fix
  applies to capture going forward. A note documents that pre-v2.62
  Gemini/Codex costs may under-count cache writes.

## Non-goals

- Multi-model split (v2.61) — composes with this; each segment is
  priced with the same corrected cache semantics.
- Re-pricing or migrating historical logs (explicitly out — plain-text
  history is immutable; we document the known under-count instead).

## Out of scope

Provider list-price drift / pricing-table freshness — that is the
existing `update-pricing` staleness mechanism, unrelated to capture.
