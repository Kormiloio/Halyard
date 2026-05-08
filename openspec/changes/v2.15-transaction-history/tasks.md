# Tasks

Implementation checklist for v2.15 — Transaction History and Config Versioning.

## 1. Rate history (shipped in session)

- [x] 1.1 Add `rate_history` field to `ClientRecord`.
- [x] 1.2 Parse `[[client.rate_history]]` in `_read_clients()`.
- [x] 1.3 Add `_effective_rate(client, as_of)` to `invoicing.py`.
- [x] 1.4 Use `_effective_rate` in `generate_invoice()`.
- [x] 1.5 Add tests for `_effective_rate` edge cases.

## 2. `halyard config history` command

- [ ] 2.1 Add `config` Typer subapp (or top-level `config-history` command).
- [ ] 2.2 Implement git-log path (parse rate diffs from `git log --patch`).
- [ ] 2.3 Implement TOML-only path (read `rate_history` entries directly).
- [ ] 2.4 Format output as a rich table.
- [ ] 2.5 Add `--client` filter.

## 3. `halyard config audit` command

- [ ] 3.1 Implement `halyard config audit`.
- [ ] 3.2 Parse invoice YAML frontmatter for period and rate data.
- [ ] 3.3 Compare invoice rates against `_effective_rate` for each invoice.
- [ ] 3.4 Print mismatch table and exit 1 if any found.
- [ ] 3.5 Add `--client` and `--period` filters.

## 4. Git reminder

- [ ] 4.1 Print git commit reminder in `halyard init` output (already done).
- [ ] 4.2 Optionally print reminder when no git repo detected and
      `_effective_rate` is used for the first time.

## 5. Tests

- [ ] 5.1 Test `config audit` with matching rates (exit 0).
- [ ] 5.2 Test `config audit` with a rate mismatch (exit 1, table output).
- [ ] 5.3 Test `config history` TOML path.
