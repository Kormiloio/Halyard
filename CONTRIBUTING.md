# Contributing to Halyard

Thanks for your interest in Halyard. The project is small enough that the
quickest way to contribute is usually to open an issue first and discuss
the change.

## Project scope: OSS only

Halyard the OSS project is **single-user, local-first, plain-text**.
The repo's intended audience is the individual developer or freelancer
who wants to instrument their own AI-assisted work. Everything that
matters for that audience — capture hooks, the AI sessions log, reports,
invoicing, dashboard, TUI, outcome graph (v3.0), usage analytics
(v2.23) — lives and stays in this repo.

A separate **Enterprise** package lives at
[Kormiloio/Halyard-Enterprise](https://github.com/Kormiloio/Halyard-Enterprise)
(`halyard_enterprise` Python package): multi-user org admin, cost
centers, organization-level rollups, hosted sync, trust aggregation
across contributors, the attestable AI work appendix (signed,
recipient-verifiable proof artifact). **That work belongs in the
enterprise repo, not here.**

The enterprise package depends on OSS Halyard as a library — it reads
the same `ai-sessions.log` format and reuses pure helpers like
`halyard.trust`. Bug fixes to OSS surfaces that also exist in
enterprise should be applied in both repos.

## What belongs in the enterprise repo

If your change touches any of these concepts, it belongs in the
[Halyard-Enterprise](https://github.com/Kormiloio/Halyard-Enterprise)
repository, not here:

- `org.toml` schema, `OrgConfig` / `Department` / `Team` / `Member`
  data model
- `halyard org` CLI subcommands
- `halyard report org` and `halyard report export` (finance CSV)
- Cost-center allocation
- Cross-contributor sync into an org store
- Attestable AI work appendix (signed appendix + recipient verifier)
- Hosted dashboards
- SSO / RBAC

## What kind of contributions are welcome here

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
- Multi-user / org-admin features (see Enterprise above).

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
