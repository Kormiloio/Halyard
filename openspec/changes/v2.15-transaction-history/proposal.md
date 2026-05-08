# Proposal: v2.15 — Transaction History and Config Versioning

## Why

Invoices reference billing rates. If a client rate changes and the history is
not preserved, it becomes impossible to audit whether past invoices used the
correct rate. The same applies to project rates and other configuration that
affects financial calculations.

Additionally, when something looks wrong in a report or invoice, there is no
way to see what the configuration looked like at the time it was generated.

## What changes

### Rate history in `clients.toml` (already shipped in v2.11)

`ClientRecord.rate_history` allows a list of `[[client.rate_history]]` entries
with `rate` and `effective` fields. The invoicing engine uses
`_effective_rate(client, as_of)` to pick the rate that was in effect on the
invoice period start date.

### `halyard config history` command

Shows a human-readable log of rate and config changes. If the project is a git
repository, this is derived from `git log --follow clients.toml`. If not, it
falls back to the `rate_history` entries in `clients.toml`.

### Git commit tip on `halyard init` and rate changes (partially shipped)

`halyard init` already prints a tip to commit `clients.toml` to git.

`halyard` should also remind the user to commit after a rate change is
detected — specifically, when a `[[client.rate_history]]` entry is written or
when `hourly_rate` changes.

### `halyard config audit` command

Cross-checks invoice line items against the rate history to confirm that each
invoice used the correct rate for its billing period. Reports any mismatches as
warnings.

## What stays the same

- `clients.toml` remains a human-editable TOML file.
- No database or shadow file is required.
- Git is recommended but not required.

## Out of scope

- Automatic git commits on rate change.
- Cryptographic signing of invoices.
- Immutable append-only rate ledger (future work).

## Success criteria

- `halyard config history` prints a table of rate changes with dates and
  old/new values.
- `halyard config audit` exits with code 0 when all invoice rates match
  history, and code 1 with a warning table when mismatches are found.
- `_effective_rate` is covered by tests for all edge cases (no history,
  one entry, entry before/after invoice date).
