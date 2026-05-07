# Proposal: v3 — Org Admin Dashboard

## Why

The local Glass Cockpit shows one user's AI work. Enterprise buyers need the
rollup: what are teams spending, which projects are AI-heavy, where are
collectors missing, and what is the organization getting for its AI investment?

At JPMC-scale, the dashboard must support tens, hundreds, or thousands of
contributors while preserving the same local ledger contract.

## What changes

Define an organization admin dashboard that ingests normalized Halyard session
records and exposes manager, director, CIO, and finance views:

- executive AI spend and adoption;
- team/project/user rollups;
- model and tool mix;
- collector health;
- unattributed session cleanup;
- finance cost allocation;
- governance and audit views.

## What stays the same

- Local files remain source of truth for contributors.
- Prompt/code content is not captured by default.
- Cloud sync is additive for organizations.
- Cost trust labels remain visible: captured, calculated, allocated, inferred,
  missing.

## Out of scope

- Full multi-tenant implementation in this change.
- Prompt/code surveillance.
- Exact ROI scoring without user-defined outcomes.
- Replacing BI/accounting systems.

## Success criteria

- Product requirements cover team, director, CIO, and finance workflows.
- Specs define org-level rollup and governance requirements.
- Future implementation can ingest 500+ users without changing local log
  semantics.

## Product reference

See `docs/PRD-org-admin-dashboard.md`.
