# PRD: Halyard Org Admin Dashboard

## Summary

Halyard needs an organization dashboard for managers, directors, and CIO/CTO
buyers who want to understand AI work across teams. The solo Glass Cockpit
proves local capture. The org admin dashboard rolls up many local ledgers into
portfolio-level intelligence.

The core question changes from:

> What did my AI-assisted work cost today?

to:

> What is our organization getting for its AI investment?

## Users

### Team manager

Manages 10-20 people and wants project-level AI usage, cost, adoption, and
unattributed work that needs cleanup before billing or reporting.

### Engineering director

Manages 60-150 people across teams and wants spend by team, project, tool,
model, and trend.

### CIO / CTO / enterprise buyer

Manages 500+ people and wants AI investment visibility, governance,
compliance/audit posture, vendor concentration, cost allocation, and ROI
signals.

### Finance / operations

Needs cost center allocation, vendor spend reconciliation, budget alerts, and
exports into BI or accounting systems.

## Goals

- Roll up `ai-sessions.log` records across many users and projects.
- Show AI spend by org, department, team, project, user, tool, and model.
- Separate captured, calculated, allocated, inferred, and missing costs.
- Surface unattributed sessions and collector health gaps.
- Support manager and CIO-level summaries without exposing prompt/code content.
- Preserve the local-first source-of-truth model for individual contributors.

## Non-Goals

- Replace the local Glass Cockpit.
- Require prompt or code capture.
- Build compliance surveillance as the default product posture.
- Make cloud sync mandatory for solo users.
- Provide exact ROI claims without user-defined outcome metrics.

## Core Views

### Executive Overview

Shows total AI spend, active users, sessions, model mix, tool mix, spend trend,
and high-level adoption.

### Teams

Shows team-level spend, sessions, active users, project mix, collector health,
and attribution quality.

### Projects

Shows AI cost and human time by project, with model/tool breakdown and
unattributed work.

### People

Shows adoption and usage by user. This should be manager-safe: visibility into
work patterns and costs, not private prompt contents.

### Governance

Shows missing collectors, unknown models, unattributed sessions, policy
violations, seat allocation gaps, and export readiness.

### Finance

Shows cost center allocation, vendor/tool spend, direct API cost, allocated
seat cost, credit usage, and monthly budget variance.

## Data Model

The org dashboard ingests normalized session records derived from local
`ai-sessions.log` files. Required org-level fields:

- organization id;
- user id;
- team id;
- project id;
- tool;
- model;
- source;
- timestamps;
- token counts;
- cost fields;
- trust labels;
- attribution state.

Raw local logs remain the user-owned source of truth. The cloud/dashboard copy
is an indexed reporting projection.

## Trust and Privacy

- Prompt/code content is not captured by default.
- Managers see usage metadata, costs, attribution, and health.
- Sensitive content capture, if ever added, must be opt-in and policy-gated.
- Reports must distinguish measured data from allocated estimates.

## Success Metrics

- A team manager can identify unattributed or unhealthy capture in under one
  minute.
- A director can see spend by team/project/model for a month.
- A CIO can answer vendor concentration and AI investment trend questions.
- Finance can export cost allocation by cost center.
- The system can ingest records from at least 500 users without changing the
  local file format.
