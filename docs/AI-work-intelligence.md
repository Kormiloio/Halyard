# AI Work Intelligence

**Status:** Current strategic framing. For the near-term build sequence, see
[`current-direction.md`](current-direction.md).

Halyard is local-first infrastructure for understanding AI-assisted work.

The first version of Halyard captures human time, AI sessions, model usage,
token counts, costs, project attribution, and invoice evidence. That foundation
can support a broader goal: helping individuals and teams understand how AI is
being used in real work, across tools and projects, without requiring prompt or
source code capture.

## Why This Matters

AI-assisted development is no longer just autocomplete. Modern work can involve:

- coding agents;
- terminal agents;
- IDE assistants;
- model routers;
- MCP servers;
- tool calls;
- subagents;
- human review loops;
- git branches and pull requests;
- calendar blocks for focused AI collaboration.

Most existing tools only see one slice of that work. Halyard's local ledger
captures metadata where the work happens and turns it into reports that are
auditable, explainable, and owned by the user.

## Core Principles

### Local-first

The local files remain the source of truth. Halyard should work without a cloud
account, and users should be able to inspect the data it captures.

### Plain text

AI work metadata should be stored in durable, readable formats such as
`ai-sessions.log`, `time.timeclock`, and TOML configuration files.

### Minimal capture

Halyard captures work metadata by default, not prompts, conversation content, or
source code. Sensitive content capture, if ever added, should be explicit,
opt-in, and policy controlled.

### Trust-labeled reporting

Reports should distinguish measured data from calculated, allocated, or inferred
data. Halyard should show uncertainty instead of hiding it.

### Tool neutrality

AI work spans many tools. Halyard should normalize session metadata across
providers and interfaces rather than tying the ledger to one vendor.

## Data We Want To Understand

Halyard already captures:

- session start and end time;
- tool;
- model;
- input and output tokens;
- cache tokens where available;
- cost;
- project;
- git branch;
- billing model;
- capture source.

Future session metadata can include:

- session id;
- wall time;
- agent active time;
- tool call count;
- tool error count;
- code additions and deletions;
- approval or rejection counts;
- MCP server usage;
- agent and subagent counts;
- test and pull request signals where available;
- resume commands for tools that support them.

Not every tool will expose every field. Halyard should preserve source and trust
metadata so users know how each number was captured.

## Individual Workflows

For individuals and freelancers, AI work intelligence should answer:

- What did I work on?
- How much human time did it take?
- Which AI tools and models did I use?
- What did those AI sessions cost?
- Which client or project should the work be attributed to?
- What evidence can I safely include with an invoice?
- Can I produce a signed, verifiable proof artifact without exposing prompts
  or source code?

## Team And Organization Workflows

For teams, AI work intelligence can support:

- spend by team, project, tool, and model;
- collector health;
- unattributed session cleanup;
- cost center allocation;
- duplicate effort detection;
- AI-assisted work trends;
- governance over agents, MCP servers, and tool usage.

Any team or enterprise layer should be additive. It should ingest a reporting
projection of local metadata without changing what the local files mean.

## Future Directions

### Attestable AI Work Appendix

The current next proof-of-work feature is a signed, verifiable appendix that a
freelancer, consultant, or small AI shop can attach to an invoice or
deliverable. The recipient can verify the artifact was not modified, while the
artifact preserves Halyard's privacy contract: no prompts, no transcripts, no
source code, and no file contents.

This is the near-term bridge from individual value to team pull. A recipient
who trusts one appendix may ask other contractors or teams to provide the same
kind of evidence.

### Security And Integrity Hardening

Before broad sharing or enterprise aggregation, Halyard must make the local
ledger more defensible: dashboard write safety, log locking, correction
records, pricing-table integrity, cache migrations, and clearer audit trails.

### Calendar Blocks

Users may want to reserve focused time for AI collaboration, just as they reserve
time for meetings or deep work. Halyard could create local calendar events for
planned AI work and later compare planned time with captured sessions.

Calendar scheduling is not the current wedge. It is deferred until the proof
and integrity surfaces are stronger.

### Work Quality Signals

Halyard should avoid claiming exact ROI from metadata alone. Instead, it can
surface quality and effectiveness signals such as:

- high tool error rates;
- repeated sessions on the same branch or ticket;
- high code churn;
- AI-heavy work followed by failing tests;
- long wall-clock sessions with little active agent time;
- heavy AI usage with no associated pull request or deliverable.

These signals are not judgments by themselves. They are prompts for review.

Outcome/work-quality analytics are gated on design-partner pull. They should
not become the next build priority until real users ask for them.

### Duplicate Effort Detection

Teams may benefit from knowing when multiple people are using AI tools to work
on similar problems. Privacy-preserving signals can include repo, project,
branch, ticket, and timing overlap.

### Agent And MCP Inventory

As AI workflows become more agentic, teams will need to understand which agents,
MCP servers, and external tools are being used. Halyard can track this as
metadata without capturing private content.

## Design Constraint

Halyard should remain useful as a local solo tool even as it grows toward team
and organization reporting.

The local product earns trust by staying simple, inspectable, and owned by the
user. Larger reporting layers should build on that foundation rather than
replacing it.
