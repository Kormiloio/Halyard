# Design

## Overview

The AI Work Ledger is an analytics and evidence layer over existing local
files. It does not replace `time.timeclock` or `ai-sessions.log`. It joins and
enriches them with local configuration about AI plans, seats, credits, and
allocation rules.

The core design goal is to preserve raw capture while making cost attribution
useful enough for freelancers and teams.

## Files

### Existing files

- `time.timeclock` tracks human work time in hledger-compatible format.
- `ai-sessions.log` tracks raw AI usage sessions.
- `clients.toml` and `projects.toml` define attribution targets.

### New file: `ai-plans.toml`

`ai-plans.toml` stores local plan, seat, and credit configuration. It belongs
in the Halyard project when costs are business/project-specific. Future
per-user defaults may live in `~/.halyard/config.toml`.

Example:

```toml
[[plan]]
slug = "claude-max"
tool = "claude-code"
billing = "seat"
monthly_usd = 200
allocation = "active_minutes"
starts_on = "2026-05-01"

[[plan]]
slug = "cursor-pro"
tool = "cursor"
billing = "credits"
monthly_usd = 20
included_credits = 500
allocation = "credits"
starts_on = "2026-05-01"

[[plan]]
slug = "anthropic-api"
tool = "claude-api"
billing = "api"
allocation = "direct"
```

## Cost model

### Direct API cost

For `billing=api`, Halyard uses the `cost_usd` already snapshotted in
`ai-sessions.log`.

### Credit cost

For `billing=credits`, Halyard uses explicit `credits=` values when present
and derives USD cost from configured plan exchange rates. If the rate is
unknown, reports show credits but leave USD as unknown.

### Seat cost

For `billing=seat`, raw sessions remain `cost_usd=0.0000`. Reports allocate a
share of the monthly seat cost using the configured rule:

- `active_minutes`: allocate by AI session duration.
- `session_count`: allocate evenly across sessions.
- `project_weight`: allocate by manually configured project weights.
- `manual`: do not allocate unless the user provides overrides.

Allocated costs are report-derived. They are never written back into
`ai-sessions.log`.

## Attribution

Attribution starts with `project=` on AI session records. If an AI session does
not have a project, Halyard may infer it from the active timer window, current
working directory, or explicit user correction. Inferred attribution must be
shown as inferred in reports until confirmed.

Future versions may add `task_id`, `deliverable`, or `job_id` conventions.
`job_id` already exists in the v1 schema and should be used for long-running
agentic jobs.

## Reporting

`halyard report` gains AI work ledger views:

```bash
halyard report --project acme/auth-migration
halyard report --client acme --month last
halyard report --ai-costs --all
```

Reports include:

- human hours;
- AI session count;
- active AI minutes;
- input and output tokens;
- cache read and write tokens;
- direct API cost;
- allocated plan/seat cost;
- total AI cost;
- total cost by tool and model;
- unattributed or inferred sessions needing review.

## Invoice evidence

`halyard invoice` can generate an optional markdown appendix:

```bash
halyard invoice acme --month last --include-ai-evidence
```

The appendix should include concise evidence:

- date range;
- tools used;
- models used;
- session count;
- token totals when available;
- direct and allocated AI costs;
- notes about estimated costs.

The appendix must not include prompts, code contents, or sensitive transcript
data by default.

## Trust and uncertainty

Reports must distinguish:

- captured: directly recorded from a tool or API response;
- calculated: deterministic from captured data and pricing;
- allocated: derived from a configured plan allocation rule;
- inferred: attribution guessed from context.

This is critical because client-facing evidence should be honest about what is
known versus estimated.
