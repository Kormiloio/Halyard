# Tasks: v2.1 — Dynamic Pricing Sync

## Spec & design
- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/pricing-sync.md

## `pricing/models.toml` (repo root)
- [x] Create `pricing/models.toml` with current model prices matching the bundled `PRICING` dict
- [x] Include optional `cache_read_multiplier` / `cache_write_multiplier` where applicable

## `src/halyard/pricing.py` changes
- [x] Add `load_pricing_table() -> dict[str, tuple[float, float]]`
  - Reads `~/.halyard/pricing.toml` if present (silently ignore on parse error)
  - Merges with bundled `PRICING` dict (local overrides bundled)
  - Caches result in module-level variable (computed once per process)
- [x] Add `pricing_table_age_days() -> int | None`
  - Returns days since mtime of `~/.halyard/pricing.toml`, or `None` if absent
- [x] Add `update_pricing(timeout: int = 5) -> tuple[int, int]`
  - Fetches `https://raw.githubusercontent.com/Kormiloio/Halyard/main/pricing/models.toml`
  - Validates: `[models]` table present, each entry has positive `input`/`output`, ≥3 models
  - On failure: raises `PricingFetchError` with human-readable message; does not modify local file
  - On success: writes atomically (temp file + rename), returns `(new_count, updated_count)`
- [x] Update `calculate_cost()` to call `load_pricing_table()` instead of reading `PRICING` directly
- [x] Update `model_is_known()` to check merged table

## `src/halyard/cli.py` — `halyard update-pricing`
- [x] Add `update-pricing` command
  - Calls `update_pricing()`
  - On success: print "Updated: N models added, M prices changed." + file path
  - On failure: print error message, "Bundled pricing table is still active.", exit code 1

## `halyard report` — staleness warning
- [x] Call `pricing_table_age_days()` in `report` command
- [x] If result is `None` or `>= 30`: print staleness warning before report output

## Tests (`tests/test_pricing.py`)
- [x] `test_load_pricing_table_no_local_file` — returns bundled table
- [x] `test_load_pricing_table_local_overrides_bundled` — local price wins for shared model
- [x] `test_load_pricing_table_local_adds_new_model` — model only in local file returns cost
- [x] `test_load_pricing_table_corrupted_local` — silently falls back to bundled table
- [x] `test_pricing_table_age_days_absent` — returns None
- [x] `test_pricing_table_age_days_fresh` — returns small integer
- [x] `test_update_pricing_success` — writes file, returns correct counts
- [x] `test_update_pricing_network_error` — raises PricingFetchError, no file written
- [x] `test_update_pricing_validation_too_few_models` — raises PricingFetchError
- [x] `test_update_pricing_validation_non_positive_price` — raises PricingFetchError
- [x] `test_update_pricing_atomic_write` — temp file renamed, existing file replaced

## Quality
- [x] Run full test suite — all passing (202 tests)
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
