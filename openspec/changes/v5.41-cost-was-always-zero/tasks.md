# v5.41 — Tasks

## Rates

- [x] `PRICING` (bundled, offline path): add `claude-opus-5`,
      `claude-sonnet-5`, `gpt-5.6-sol`, `gpt-5.6-terra`,
      `gemini-3.6-flash`.
- [x] Correct `claude-opus-4-7` (15/75 → 5/25) and `claude-haiku-4-5`
      (0.80/4.00 → 1/5), both variants of the haiku key.
- [x] Mirror all of the above into `pricing/models.toml` with per-model
      cache multipliers and a refreshed `updated:` stamp.
- [x] `_coerce_multiplier` accepts `0` so a free cache write is
      expressible; negative still rejected.
- [x] Quote every dotted model key. **Found a shipped bug:**
      `gemini-2.5-pro` and `gemini-2.5-flash` were bare-dotted, so neither
      has ever existed as a key in the remote table.

## Local models

- [x] `_LOCAL_MODEL_MARKERS` + `model_is_local()` move from `junie.py`
      to `collectors/__init__.py`; `junie` imports from there.
- [x] `claude_code` and `codex_app` classify local models as
      `billing="local"` with cost `0.0`.

## Pricing the unpriced

- [x] ~~`codex_app` prices through `calculate_cost`~~ — **not done, by
      design.** Codex reports no cost of its own, so the collector has no
      evidence a read-time lookup lacks, and writing a figure at import
      would freeze the rate into the row exactly as the stale table did.
      `resolve_costs` supplies it. See `design.md`.
- [x] `pricing.cost_is_known(model, billing)` — derived, not stored.
      Checks the model *name* as well as stored billing, so pre-v5.41
      local rows read as known-free rather than unpriced.
- [x] `ai_log.resolve_costs(sessions)`, called in `parse_sessions` after
      the v5.40 collapse. Never overwrites a non-zero cost.

## Surfaces

- [x] Model table renders `n/a` for unpriced rows instead of `$0.00`, and
      excludes them from the share denominator.
- [x] `CostBucket.priced` carries the distinction to the surfaces.
- [x] `doctor` check `pricing.unpriced` naming the models and counts.

## Tests (`tests/test_v541_cost_basis.py`, 30)

- [x] Each new rate returns the hand-computed cost.
- [x] The two corrected entries return the new rate, not the old.
- [x] A zero cache-write multiplier is accepted; a negative one rejected.
- [x] Local models recognised from the shared classifier; hosted are not.
- [x] A local row is known-free, including one recorded as `api`.
- [x] `resolve_costs` prices a zero-cost row on a known model.
- [x] `resolve_costs` never overwrites a non-zero cost.
- [x] `resolve_costs` leaves local and unpriced rows at zero.
- [x] The shipped table parses to flat keys and agrees with the bundled
      dict — the test that found the `gemini-2.5-*` bug.

## Adjusted existing tests

- [x] `test_haiku_mixed_cost` asserted `$0.80/$4.00` — Haiku *3.5*'s rate.
      It was locking in the understatement; updated to `$1/$5`.
- [x] `test_costs_panel_zero_cost_no_credits_shows_missing` used `gpt-4o`,
      which v5.41 now prices at read time. Retargeted to an unpriced model
      so it still covers the "missing" path it was written for.

## Verified against real data

- [x] The live hub reprices from `$0.00` to **$839.70** across 98 rows.
- [x] The two `muse-glimmer:30b-mlx` rows read known-free, not unpriced,
      without a re-import.
- [x] `gpt-oss-120b-medium` and `github-copilot` correctly read unpriced.

## Gates

- [x] `uv run pytest` — **1982 passing**.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/` — clean, 105 files.

## Docs

- [ ] Roadmap entry in `openspec/project.md`.
- [ ] `CHANGELOG.md` under Unreleased.
