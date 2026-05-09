# Current Direction

This is the public orientation doc for Halyard's current product direction.
Older PRDs remain in `docs/` as historical design records, but this page and
the active OpenSpec changes are the best guide to what Halyard is trying to
become now.

## The Product

Halyard is the open AI work ledger.

For individuals and small AI shops, Halyard helps prove AI-assisted work:
what happened, what tools were used, what it cost, which project it belonged
to, and what can be safely shown to a client without exposing prompts or code.

For teams and enterprises, the same ledger becomes AI Work Intelligence:
cross-tool visibility, trust-labeled cost allocation, governance, and later
effectiveness signals. Enterprise aggregation is additive. It must not break
the local-first source of truth.

## The Wedge

The near-term wedge is proof of work for AI-assisted engineering.

The local product must be useful before any team or enterprise layer exists:

- capture AI sessions across tools;
- keep logs local and inspectable;
- track human time and AI spend by project;
- explain measured versus estimated cost with trust labels;
- generate invoice-safe evidence;
- help users clean up unattributed sessions;
- never capture prompts or source code by default.

The next network-effect feature is the attestable AI work appendix: a signed,
verifiable, privacy-preserving artifact that an individual can attach to an
invoice, deliverable, or review packet.

## Current Build Sequence

The current sequence is:

1. Security and distribution hardening.
2. Log integrity and shared timer orchestration.
3. Cache, audit, and pricing-table hardening.
4. Attestable AI work appendix.
5. Outcome graph only if design partners ask for it.
6. Org and enterprise reporting only after the local proof artifact and
   security posture are credible.

## What Is Deferred

These ideas are important, but not the current wedge:

- broad hosted dashboards;
- SSO/RBAC;
- org admin dashboards;
- outcome graph analytics;
- duplicate-effort detection;
- calendar scheduling for AI work;
- new collectors beyond the currently supported tools.

They should be built when user pull or design-partner evidence justifies them.

## Governing Principles

- Local-first by default.
- Plain text as the durable source of truth.
- No prompt or source-code capture by default.
- Trust labels instead of fake certainty.
- Open-source core, paid sharing/governance later.
- Build for individual voluntary adoption before enterprise aggregation.
