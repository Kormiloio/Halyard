# Spec: Rate History and Config Versioning

## `_effective_rate(client, as_of)` (invoicing.py — shipped)

```python
def _effective_rate(client: ClientRecord, as_of: date) -> float
```

- If `client.rate_history` is empty, returns `client.hourly_rate`.
- Otherwise, filters entries where `entry_date <= as_of`.
- Returns the rate from the entry with the latest date.
- If no entry qualifies (all entries are after `as_of`), returns
  `client.hourly_rate`.

## `halyard config history` (cli.py)

```
halyard config history [--client <slug>]
```

- Reads `clients.toml` from the current project dir.
- If in a git repo: derives history from `git log --follow --patch`.
- Otherwise: reads `[[client.rate_history]]` entries.
- `--client` filters output to a single client slug.
- Output: rich table with columns Client / Date / Rate / Source.

## `halyard config audit` (cli.py)

```
halyard config audit [--client <slug>] [--period YYYY-MM]
```

- Scans `invoices/` for YAML-fronted invoice files.
- For each invoice, resolves the effective rate for the invoice period.
- Compares to the rate stored in invoice line items.
- Prints a mismatch table if any discrepancies found.
- Exit code 0 = clean, 1 = mismatches found.

## TOML format for rate history

```toml
[[client]]
slug = "acme"
hourly_rate = 175   # current/default rate

[[client.rate_history]]
effective = "2025-01-01"  # ISO date
rate = 150

[[client.rate_history]]
effective = "2026-01-01"
rate = 175
```

The `hourly_rate` field on `[[client]]` is the fallback when no history entry
applies to the billing period. It should always reflect the current rate.
