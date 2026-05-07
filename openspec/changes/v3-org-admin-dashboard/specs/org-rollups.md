# Org Rollups Spec

## Requirement: executive overview

The org dashboard MUST summarize AI work across the organization.

### Scenario: CIO monthly overview

- WHEN a CIO opens the dashboard for a month
- THEN they see total AI spend, active users, sessions, model mix, tool mix,
  and trend versus the prior period

### Scenario: vendor concentration

- WHEN one model provider accounts for most spend
- THEN the dashboard highlights provider concentration risk

## Requirement: team rollups

The org dashboard MUST summarize AI usage by team.

### Scenario: manager team view

- WHEN a manager opens their team
- THEN they see AI sessions, spend, active users, project breakdown, and
  collector health for their team

### Scenario: attribution gaps

- WHEN team sessions are missing project attribution
- THEN the dashboard shows a needs-attention count
- AND does not silently allocate those costs to projects

## Requirement: finance rollups

The org dashboard MUST support finance cost allocation.

### Scenario: cost center export

- WHEN finance exports a billing period
- THEN the export includes cost center, project, team, tool, model, direct
  cost, allocated cost, and trust labels

### Scenario: mixed trust aggregate

- WHEN a total contains captured and allocated costs
- THEN the dashboard labels the aggregate as mixed trust
