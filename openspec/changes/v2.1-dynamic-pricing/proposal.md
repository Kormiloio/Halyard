# Proposal: v2.1 — Dynamic Pricing Sync

## Why this change

`pricing.py` ships a hardcoded table of model prices snapshotted at release
time. This breaks cost accuracy in a predictable and accelerating way:

- Models drop prices frequently (Google cut Gemini 2.5 Flash pricing twice in
  three months; Anthropic cut Haiku pricing 80% between releases).
- New models ship between Halyard releases and get `cost_usd=0.0000` because
  they're not in the table.
- A user running a six-month-old Halyard version is calculating costs against
  prices that may be 50% wrong.

The PRD-halyard.md lists this as an open question. The question is now answered
enough to spec: fetch from a source Halyard controls, store locally, fall back
to the bundled table.

## What this change does

### 1. `halyard update-pricing`

A new CLI command that fetches a canonical pricing TOML from a known URL,
validates the structure, and saves it to `~/.halyard/pricing.toml`. On next
run, all cost calculations use the updated table.

### 2. Pricing source

A file hosted at a stable URL in the Halyard GitHub repository
(`main` branch, `pricing/models.toml`). This keeps the source under the same
MIT license, auditable by anyone, and updatable without a Halyard release.

The format is TOML, consistent with Halyard conventions:

```toml
# Halyard model pricing table — https://halyard.dev/pricing
# updated: 2026-05-07
# All prices are USD per million tokens.

[models]

[models.claude-opus-4-7]
input  = 15.00
output = 75.00

[models.gemini-2.5-flash]
input  = 0.15
output = 0.60
cache_read_multiplier  = 0.25   # optional; defaults to 0.10 if absent
cache_write_multiplier = 1.25   # optional; defaults to 1.25 if absent
```

### 3. Fallback chain

Cost calculation checks:
1. `~/.halyard/pricing.toml` (user-fetched, most recent)
2. Bundled table in `pricing.py` (ships with Halyard, never removed)
3. `0.0000` for unknown models (existing behaviour, unchanged)

The bundled table remains accurate at release time. The fetched table extends
and overrides it. A model present in both uses the fetched price.

### 4. Staleness warning

`halyard report` and `halyard dashboard` show a soft warning when
`~/.halyard/pricing.toml` is absent or older than 30 days:

```
⚠  Pricing table last updated 45 days ago. Run halyard update-pricing to refresh.
```

This is a warning, not an error. Old prices are better than no prices.

## What this change does NOT do

- No automatic background updates. The user runs `halyard update-pricing`
  explicitly. Automatic network calls from hook processes would be surprising
  and violate the local-first principle.
- No per-user or enterprise pricing overrides in this version. Custom pricing
  (enterprise agreements, negotiated rates) is a future concern.
- No pricing for credit-based tools (Cursor credits, Codex). Those have no
  public per-token rate.
- No validation that prices are "correct" — we can't know. We validate
  structure only (positive numbers, known fields).

## Key decisions

**Why a GitHub-hosted file and not a third-party source?**  
We control the format, the update cadence, and the trust model. A third-party
source (e.g., a community YAML file from someone else's repo) introduces a
supply-chain dependency for financial data. If that repo gets compromised or
abandoned, Halyard users get wrong cost numbers silently.

**Why not fetch on every `halyard report`?**  
Network calls in the report path violate the local-first principle and add
latency. The user's internet connection may be unavailable. Explicit fetch
keeps the user in control of when the table updates.

**Why TOML and not JSON?**  
Consistency. All Halyard config files are TOML. A maintainer editing the
pricing file should use the same format as `halyard.toml`.

## Success criteria

- `halyard update-pricing` fetches, validates, and saves in under 3 seconds on
  a normal connection.
- After running it, `halyard report` shows costs calculated with the new prices
  for future sessions (not retroactively — past sessions have snapshotted cost).
- A model not in the bundled table but present in the fetched table gets correct
  cost attribution.
- If the fetch fails (no network, bad response), the command fails clearly and
  the bundled table continues to work.
- `halyard report` shows a staleness warning after 30 days without an update.
