# Spec: Cache-Aware Cost Correctness

## Requirement: Single token contract

Every collector MUST emit `input_tokens` as **fresh, non-cached input
only**. Cached tokens MUST appear solely in `cache_read` /
`cache_write`. No token may be counted in both.

### Scenario: cache-inclusive source normalised
- GIVEN a collector whose raw payload reports input inclusive of
  838,991 cached tokens within 1,022,341 input
- WHEN the session is constructed
- THEN `input_tokens` = 183,350 (fresh) and `cache_read` = 838,991;
  cost bills fresh at 1.0× and cache at the cache multiplier — never
  the cached tokens at both.

### Scenario: already-exclusive source unchanged
- GIVEN a collector whose input already excludes cache
- THEN tokens and cost are byte-identical to pre-v2.62.

## Requirement: Capture cache writes everywhere available

Gemini and Codex collectors MUST populate `cache_write` when the
source exposes cache-creation tokens; `None` when it does not
(never `0` by assumption).

## Requirement: No pricing-table change

The fix MUST be at capture only. `_CACHE_READ_MULTIPLIER` /
`_CACHE_WRITE_MULTIPLIER` and per-model overrides are unchanged; trust
labels unchanged.

## Requirement: History not rewritten

Pre-v2.62 `ai-sessions.log` lines MUST NOT be modified. The known
pre-fix Gemini/Codex cache-write under-count MUST be documented in the
ledger PRD rather than retro-corrected.

## Requirement: Composes with multi-model (v2.61)

When a session has a per-model breakdown, each segment MUST be priced
with the corrected cache semantics independently.
