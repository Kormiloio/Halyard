# Proposal: v2 — AI Work Ledger

## Why

Halyard started as a local-first time, expense, and invoicing tool for
freelancers. That remains useful, but AI-assisted work changes what must be
tracked.

When a client hires Mario to build something with AI, the work is no longer
only human hours. It is human direction plus AI sessions, model choices, token
usage, cache behavior, API spend, credits, subscriptions, and tool-specific
resources. Existing time trackers do not see the AI layer. Vendor dashboards do
not know the client or project. Accounting tools only see monthly bills.

Halyard should become the user-owned ledger of AI labor and AI spend.

## What changes

This change extends the v1 AI session foundation into a project-level AI work
ledger. It introduces:

- plan and subscription cost configuration;
- AI work attribution beyond raw sessions;
- combined human time plus AI cost reports;
- invoice evidence for AI-assisted work;
- explicit handling of API, credit, and seat billing models;
- clearer local data contracts for future team sync.

## What stays the same

- The freelancer time and invoice workflow remains intact.
- `time.timeclock` remains the source of truth for human time.
- `ai-sessions.log` remains the append-only source of truth for AI sessions.
- Cloud sync is optional and not required for the local workflow.
- User data remains plain text and owned by the user.

## Out of scope

- Multi-tenant cloud dashboard.
- Required payment processing.
- Automatic capture of private prompts or code contents.
- Exact per-session vendor billing for tools that only expose monthly seats.
- Replacing full accounting systems.

## Success criteria

- A user can configure AI plans and API pricing assumptions locally.
- `halyard report` shows human hours, AI sessions, tokens, direct API cost,
  allocated plan cost, and total AI cost by project.
- Halyard can generate a markdown invoice appendix with AI usage evidence for a
  client and date range.
- Reports clearly label estimated or allocated costs.
- The data model can later sync to a team dashboard without transformation.

## Product reference

See `docs/PRD-ai-work-ledger.md` for the product requirements and strategic
framing behind this change.
