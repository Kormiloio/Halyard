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

## Requirement: project rollups

The org dashboard MUST show AI cost and human time combined at the project level.

### Scenario: project detail view

- WHEN a manager drills into a project
- THEN they see AI session count, total cost, human hours, model/tool breakdown,
  and unattributed session count for the selected billing period

### Scenario: project with no AI sessions

- WHEN a project has human time entries but no AI sessions
- THEN the project view still renders human hours
- AND notes that no AI usage was captured

### Scenario: cross-team project

- WHEN contributors from multiple teams work on the same project
- THEN the project view shows a per-team breakdown of sessions and cost
- AND the total is the sum across all teams

---

## Requirement: people and adoption view

The org dashboard MUST show per-user AI adoption in a manager-safe way.

### Scenario: team adoption summary

- WHEN a manager opens the people view for their team
- THEN they see per-user session count, active days, tool mix, and total cost
  for the period
- AND they do not see prompt text, code contents, or session transcripts

### Scenario: inactive user detection

- WHEN a team member has not captured any AI sessions in the period
- THEN the people view flags them as "no capture"
- AND the governance view counts them toward collector health gaps

### Scenario: adoption trend

- WHEN a director views adoption over time
- THEN the chart shows active users per week and sessions per user per week
  over the last 90 days

---

## Requirement: finance rollups

The org dashboard MUST support finance cost allocation.

### Scenario: cost center export

- WHEN finance exports a billing period
- THEN the export includes cost center, project, team, tool, model, direct
  cost, allocated cost, and trust labels

### Scenario: mixed trust aggregate

- WHEN a total contains captured and allocated costs
- THEN the dashboard labels the aggregate as mixed trust
