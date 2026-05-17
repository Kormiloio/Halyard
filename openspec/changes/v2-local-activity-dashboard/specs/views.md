# Dashboard Views Spec

## Requirement: modern operational UI

The dashboard MUST feel like a modern operational bridge for AI work.

### Scenario: dense working interface

- WHEN the dashboard renders
- THEN it uses compact metrics, dense tables, status indicators, and restrained
  charts suited for repeated work
- AND it does not present the core app as a marketing landing page

### Scenario: semantic status colors

- WHEN health, attribution, or cost states are shown
- THEN healthy capture uses a positive status treatment
- AND inferred or needs-review states use a warning treatment
- AND broken capture, missing files, or unwritable logs use an error treatment

### Scenario: stable live layout

- WHEN new sessions are captured or costs update
- THEN core dashboard regions keep stable dimensions
- AND the UI does not jump, resize, or obscure neighboring content

### Scenario: responsive cockpit

- WHEN the dashboard is viewed on laptop and desktop widths
- THEN the primary metrics, session stream, and health states remain legible
- AND text does not overlap or overflow its containers

## Requirement: project summary

The dashboard MUST summarize human and AI work by project.

### Scenario: project has combined activity

- WHEN a project has timeclock entries and AI sessions
- THEN the Projects view shows human hours, AI session count, AI cost, top
  tool, and top model

### Scenario: project has unattributed AI sessions nearby

- WHEN unattributed AI sessions overlap a project's human timer window
- THEN the Projects view shows a possible attribution warning
- AND does not silently assign the sessions to that project

## Requirement: session stream

The dashboard MUST expose the AI session stream in a readable form.

### Scenario: filter by project

- WHEN the user filters sessions by project
- THEN the Sessions view shows only matching sessions

### Scenario: filter by model

- WHEN the user filters sessions by model
- THEN the Sessions view shows only matching sessions

### Scenario: unknown fields

- WHEN a session contains future `key=value` fields
- THEN the Sessions view still renders the known fields
- AND ignores unknown fields without error

## Requirement: cost view

The dashboard MUST distinguish different cost qualities.

### Scenario: direct cost

- WHEN cost comes from `cost_usd` in `ai-sessions.log`
- THEN the Costs view labels it captured or calculated

### Scenario: allocated plan cost

- WHEN cost comes from `ai-plans.toml` allocation
- THEN the Costs view labels it allocated

### Scenario: missing cost

- WHEN Halyard lacks enough information to compute cost
- THEN the Costs view marks the value as missing
- AND explains what configuration is needed

## Requirement: invoice evidence preview

The dashboard SHOULD preview client-safe invoice evidence.

### Scenario: invoice evidence preview

- WHEN a user selects a client and period
- THEN the dashboard previews tools, models, sessions, token totals, and costs
  that would be included in an invoice appendix
- AND excludes prompts, transcripts, and code contents by default
