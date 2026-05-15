# Contributing to Halyard

Thanks for your interest in Halyard. The project is small enough that the
quickest way to contribute is usually to open an issue first and discuss
the change.

## Project scope: OSS only

Halyard the OSS project is **single-user, local-first, plain-text**.
The repo's intended audience is the individual developer or freelancer
who wants to instrument their own AI-assisted work. Everything that
matters for that audience — capture hooks, the AI sessions log, reports,
invoicing, dashboard, TUI — lives and stays in this repo.

A separate **Enterprise** version is planned in its own repository:
multi-user org admin, cost centers, organization-level rollups, hosted
sync, trust aggregation across contributors. **That work belongs in the
enterprise repo, not here.**

## Frozen modules — do not extend in this repo

The following files are scaffolding for the future enterprise version
that was committed to this repo earlier in the project's history. They
are functional but **off-limits for new feature work in OSS Halyard**:

- `src/halyard/org.py` — org / department / team / member data model.
- `src/halyard/org_store.py` — org-level SQLite sync store.
- `src/halyard/org_rollups.py` — team and department rollup aggregation.
- `src/halyard/org_reports.py` — org-level CLI reports.
- `src/halyard/cost_centers.py` — cost center allocation.
- `src/halyard/sync.py` — push local sessions into the org store.
- `src/halyard/cli_org.py` — `halyard org` subcommands.

These modules will be **extracted into a separate `halyard-enterprise`
package** when the enterprise version starts. Until then:

- **Do not add new features** that touch these modules.
- **Do not extend** the `org.toml` schema, the `OrgConfig` model, or
  the `halyard org` CLI.
- **Bug fixes only**, and only when the bug affects a path a solo user
  can reach (the dashboard reading a sibling-account file, a security
  finding, etc.).
- **Do not start new openspec changes** scoped at multi-user, org admin,
  cost-center, governance, trust aggregation, or hosted sync work in
  this repo. Those proposals belong in the enterprise repo when it
  exists.

If you're unsure whether something crosses the line, ask before
implementing.

## What kind of contributions are welcome

- Bug fixes in capture hooks, the log format, reports, invoicing, the
  dashboard, the TUI.
- New collectors for AI tools that expose a public hook surface (Claude
  Code, Cursor, Gemini CLI today; file an issue first if you're
  proposing a new one).
- Documentation, README polish, troubleshooting notes.
- Tests, especially for solo-developer paths that aren't well covered.
- Privacy-preserving improvements to existing surfaces.

## What's not welcome here

- Cloud / hosted backend integrations beyond optional PyPI metadata.
- Telemetry that phones home.
- Anything that captures prompt text, source code, or full transcripts.
- Multi-user / org-admin features (see frozen modules above).

## Working with OpenSpec

Halyard uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for
spec-driven development. Larger changes live under
`openspec/changes/<slug>/` with `proposal.md`, `specs/*.md`, `design.md`,
and `tasks.md`. Completed changes get archived to
`openspec/changes/archive/YYYY-MM-DD-<slug>/`.

See [`openspec/project.md`](openspec/project.md) for full conventions.

## Development setup

```bash
uv sync
uv run pytest tests/
uv run ruff check .
uv run mypy src/halyard
```

## License

MIT. See [`LICENSE`](LICENSE).
