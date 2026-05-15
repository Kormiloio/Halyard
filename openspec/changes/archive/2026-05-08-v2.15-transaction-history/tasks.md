# Tasks

Implementation checklist for v2.15 — Transaction History and Config Versioning.

## 1. Rate history (shipped in session)

- [x] 1.1 Add `rate_history` field to `ClientRecord`.
- [x] 1.2 Parse `[[client.rate_history]]` in `_read_clients()`.
- [x] 1.3 Add `_effective_rate(client, as_of)` to `invoicing.py`.
- [x] 1.4 Use `_effective_rate` in `generate_invoice()`.
- [x] 1.5 Add tests for `_effective_rate` edge cases.

## 2. `halyard config history` command

- [x] 2.1 Add `config` Typer subapp.
- [x] 2.2 Implement git-log path (parse rate diffs from `git log --patch`).
- [x] 2.3 Implement TOML-only path (read `rate_history` entries directly).
- [x] 2.4 Format output as a rich table.
- [x] 2.5 Add `--client` filter.

## 3. `halyard config audit` command

- [x] 3.1 Implement `halyard config audit`.
- [x] 3.2 Parse invoice YAML frontmatter for period and rate data; parse rates from markdown table.
- [x] 3.3 Compare invoice rates against `_effective_rate` for each invoice.
- [x] 3.4 Print mismatch table and exit 1 if any found.
- [x] 3.5 Add `--client` and `--period` filters.

## 4. Git reminder

- [x] 4.1 Print git commit reminder in `halyard init` output (already done).
- [x] 4.2 `config history` prints reminder tip when no git repo detected.

## 5. Tests

- [x] 5.1 Test `config audit` with matching rates (exit 0).
- [x] 5.2 Test `config audit` with a rate mismatch (exit 1, table output).
- [x] 5.3 Test `config history` TOML path.
