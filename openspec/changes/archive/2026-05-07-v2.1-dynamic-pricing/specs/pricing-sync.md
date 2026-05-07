# Spec: Dynamic Pricing Sync

---

## Pricing resolution

**WHEN** `calculate_cost()` is called for a model present in `~/.halyard/pricing.toml`  
**THEN** the locally-fetched price is used

**WHEN** `calculate_cost()` is called for a model absent from the local file  
**BUT** present in the bundled `PRICING` dict  
**THEN** the bundled price is used

**WHEN** `calculate_cost()` is called for a model absent from both  
**THEN** `0.0` is returned (unchanged from current behaviour)

**WHEN** `~/.halyard/pricing.toml` is present but corrupted  
**THEN** it is silently ignored and the bundled table is used

---

## `halyard update-pricing`

**WHEN** the command runs and the network request succeeds  
**AND** the response is valid TOML with a `[models]` table  
**AND** every model entry has positive `input` and `output` values  
**THEN** `~/.halyard/pricing.toml` is written with the fetched content  
**AND** the command prints how many models were added or updated  
**AND** exits with code 0

**WHEN** the command runs and the network request fails (timeout, DNS, HTTP error)  
**THEN** `~/.halyard/pricing.toml` is not modified  
**AND** the command prints a clear error message  
**AND** exits with code 1

**WHEN** the response is valid TOML but fails validation  
(fewer than 3 models, non-positive price, missing required field)  
**THEN** `~/.halyard/pricing.toml` is not modified  
**AND** the command prints a validation error  
**AND** exits with code 1

**WHEN** `~/.halyard/pricing.toml` already exists and the fetch succeeds  
**THEN** the existing file is replaced atomically (write to temp, then rename)

---

## Staleness warning

**WHEN** `halyard report` runs  
**AND** `~/.halyard/pricing.toml` does not exist  
**THEN** a staleness warning is shown before the report

**WHEN** `halyard report` runs  
**AND** `~/.halyard/pricing.toml` exists but its mtime is ≥ 30 days ago  
**THEN** a staleness warning is shown before the report

**WHEN** `halyard report` runs  
**AND** `~/.halyard/pricing.toml` was updated fewer than 30 days ago  
**THEN** no warning is shown

**WHEN** the staleness warning is shown  
**THEN** the report still runs and produces complete output  
(the warning is informational, not blocking)

---

## Model coverage

**WHEN** a model is present in `~/.halyard/pricing.toml` but not in `pricing.py`  
**THEN** `model_is_known()` returns `True`  
**AND** `calculate_cost()` returns a non-zero cost for that model

**WHEN** a model's price changes between the bundled table and the fetched table  
**THEN** sessions captured after `update-pricing` use the new price  
**AND** sessions already written to `ai-sessions.log` keep their snapshotted cost  
(logs are never rewritten)

---

## Cache multipliers

**WHEN** a model entry in the fetched table includes `cache_read_multiplier`  
**THEN** that multiplier is used for cache read cost calculation for that model

**WHEN** a model entry does not include `cache_read_multiplier`  
**THEN** the global default (0.10) is used
