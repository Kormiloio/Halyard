# Design: Dynamic Pricing Sync

## Pricing resolution chain

`calculate_cost()` currently reads a hardcoded dict in `pricing.py`. After
this change it resolves prices through a chain:

```
~/.halyard/pricing.toml  (user-fetched, most recent)
        ↓ missing key?
pricing.py PRICING dict  (bundled, accurate at release)
        ↓ missing key?
0.0000                   (unknown model, existing behaviour)
```

The merged table is computed once per process and cached in a module-level
variable so repeated calls within a single `halyard report` don't re-read disk.

---

## Remote source format (`pricing/models.toml`)

A file in the Halyard GitHub repo at `pricing/models.toml` on `main`.
Fetch URL: `https://raw.githubusercontent.com/Kormiloio/Halyard/main/pricing/models.toml`

```toml
# Halyard model pricing table
# updated: 2026-05-07
# Prices are USD per million tokens.

[models.claude-opus-4-7]
input  = 15.00
output = 75.00

[models.gemini-2.5-flash]
input  = 0.15
output = 0.60
cache_read_multiplier  = 0.25
cache_write_multiplier = 1.25

[models.gpt-4o]
input  = 2.50
output = 10.00
```

`cache_read_multiplier` and `cache_write_multiplier` are optional per model.
If absent, the global defaults from `pricing.py` are used (0.10 and 1.25).

---

## Local storage (`~/.halyard/pricing.toml`)

Same format as the remote file. Written verbatim after fetch — no
transformation. The `updated` comment is preserved and used for staleness
detection (read the file's `mtime`, not the comment).

---

## `src/halyard/pricing.py` changes

### New public API

```python
def load_pricing_table() -> dict[str, tuple[float, float]]:
    """Return merged table: local overrides bundled. Cached per process."""

def pricing_table_age_days() -> int | None:
    """Days since ~/.halyard/pricing.toml was last written. None if absent."""

def update_pricing(timeout: int = 5) -> tuple[int, int]:
    """Fetch remote table, validate, save locally.
    Returns (new_count, updated_count) — models added or updated."""
```

`calculate_cost()` and `model_is_known()` are updated to call
`load_pricing_table()` instead of reading `PRICING` directly.

### Validation on fetch

Before saving, validate that the fetched TOML:
1. Has a `[models]` table.
2. Every model entry has `input` and `output` as positive floats.
3. Optional multipliers, if present, are positive floats.
4. Total model count is at least 3 (guards against a truncated response).

Validation failure raises `PricingFetchError` with a human-readable message.
The local file is not updated on failure.

---

## `halyard update-pricing` CLI command

```
$ halyard update-pricing
Fetching pricing table from github.com/Kormiloio/Halyard...
Updated: 3 models added, 2 prices changed.
Pricing table saved to ~/.halyard/pricing.toml.
```

On failure:
```
$ halyard update-pricing
Error: could not fetch pricing table — connection timed out.
Bundled pricing table (2026-05 snapshot) is still active.
```

Exit code 0 on success, 1 on fetch/validation failure.

---

## Staleness warning

`halyard report` and `halyard dashboard` call `pricing_table_age_days()`.
If the result is ≥ 30 (or `None` — no local file), a single warning line is
prepended to the output:

```
⚠  Pricing table last updated 45 days ago — run halyard update-pricing to refresh.
```

This is a soft warning only. It does not affect exit code or report content.

---

## `pricing/models.toml` (new file in repo root)

This file ships in the repo alongside `src/`. It serves two purposes:

1. It is the remote fetch target (via `raw.githubusercontent.com`).
2. It replaces the hardcoded `PRICING` dict as the authoritative source — at
   release time, `pricing.py`'s bundled table is generated from this file (or
   kept in sync manually; either approach is acceptable for v1).

Maintainer workflow for a price change:
1. Edit `pricing/models.toml`.
2. Push to `main`.
3. Users running `halyard update-pricing` get the new prices immediately.
4. No Halyard release required.

---

## What does NOT change

- The `cost_usd` field in existing log lines. Past sessions keep their
  snapshotted cost. Dynamic pricing only affects new sessions.
- The `calculate_cost()` function signature. Callers don't need changes.
- The `PRICING` dict in `pricing.py`. It remains as the bundled fallback,
  updated at each release from `pricing/models.toml`.

---

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| No network | `update-pricing` fails with message; bundled table used |
| Timeout (>5s) | Same |
| Malformed TOML | `update-pricing` fails with parse error; old local file kept |
| Validation failure | `update-pricing` fails; old local file kept |
| Local file corrupted | Silently ignored; bundled table used |
| Local file missing | Bundled table used; staleness warning after 30 days |
