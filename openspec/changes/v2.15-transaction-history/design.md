# Design

## Rate history data model (shipped)

`ClientRecord` carries:

```python
rate_history: tuple[tuple[date, float], ...] = ()
```

Parsed from `[[client.rate_history]]` TOML entries:

```toml
[[client]]
slug = "acme"
hourly_rate = 175

[[client.rate_history]]
effective = "2025-01-01"
rate = 150

[[client.rate_history]]
effective = "2026-01-01"
rate = 175
```

`_effective_rate(client, as_of)` returns the most recent rate with
`effective <= as_of`, falling back to `client.hourly_rate` if no history entry
qualifies.

## `halyard config history` command

Algorithm:
1. Check if `clients.toml` is inside a git repository.
2. If yes: run `git log --follow --patch clients.toml` and parse rate-change
   diffs (lines starting with `+hourly_rate` or `+rate =`).
3. If no: read `rate_history` entries from `clients.toml` and format as a
   table.

Output format (table):

```
Client   Date        Rate        Source
acme     2025-01-01  $150/hr     rate_history
acme     2026-01-01  $175/hr     rate_history
```

## `halyard config audit` command

For each generated invoice in the `invoices/` directory:
1. Parse the invoice's YAML frontmatter for `client`, `period_start`, and line
   item rates.
2. Look up `_effective_rate(client, period_start)` from current `clients.toml`.
3. Compare to the rate recorded in the invoice.
4. Report any mismatch.

Exit code 0 if clean, 1 if any mismatch found.

## Git commit reminder

When `halyard` writes a config change (future: config write commands), print:

```
Tip: commit clients.toml to preserve the rate audit trail.
```

This is already printed during `halyard init`. The audit reminder should also
appear when `_effective_rate` is first used and no git repository is detected.
