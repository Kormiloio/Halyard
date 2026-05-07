# Dashboard Spec

## Requirement: dashboard command

Halyard MUST provide a local dashboard command.

### Scenario: start dashboard

- WHEN the user runs `halyard dashboard`
- THEN Halyard starts a local web server bound to `127.0.0.1`
- AND prints the local URL
- AND does not require a cloud account

### Scenario: open browser explicitly

- WHEN the user runs `halyard dashboard --open`
- THEN Halyard opens the dashboard URL in the platform browser

### Scenario: no Halyard project

- WHEN the user runs `halyard dashboard` outside a Halyard project
- THEN Halyard exits with a clear message instructing the user to run
  `halyard init`

## Requirement: today view

The dashboard MUST show current work status.

### Scenario: active timer

- WHEN a timer is active
- THEN the Today view shows the active project and elapsed human time

### Scenario: recent AI sessions

- WHEN `ai-sessions.log` contains sessions for today
- THEN the Today view shows recent sessions, token totals, model mix, and cost

### Scenario: no captured sessions

- WHEN no AI sessions exist for today
- THEN the Today view says no AI usage has been captured today
- AND links to collector health guidance

## Requirement: Glass Cockpit overview

The dashboard MUST provide a modern cockpit-style overview as the default
working view.

### Scenario: open dashboard

- WHEN the user opens the dashboard
- THEN the first view shows active timer state, capture health, today's human
  time, today's AI sessions, token totals, AI cost, model mix, and warnings
- AND the layout is scannable without requiring navigation to multiple pages

### Scenario: live capture healthy

- WHEN the active timer is running and recent AI sessions are captured
- THEN the cockpit shows a healthy capture state
- AND displays the latest session in the recent activity stream

### Scenario: capture degraded

- WHEN hooks are missing, sessions are unattributed, or costs cannot be
  calculated
- THEN the cockpit shows prominent warning states
- AND identifies the specific issue without hiding normal project data

## Requirement: collector health

The dashboard MUST show whether capture is likely working.

### Scenario: Claude Code hook installed

- WHEN `.claude/settings.json` or `~/.claude/settings.json` contains Halyard
  hook commands
- THEN the Health view reports Claude Code capture as installed

### Scenario: hook missing

- WHEN no Halyard Claude Code hook is found
- THEN the Health view shows the hook as missing
- AND suggests `halyard install-hook`

### Scenario: log unwritable

- WHEN `ai-sessions.log` is missing or not writable
- THEN the Health view reports the issue clearly

## Requirement: local-first safety

The dashboard MUST preserve Halyard's local-first contract.

### Scenario: dashboard data source

- WHEN the dashboard renders
- THEN it reads from local project files and selected `~/.halyard/` state only
- AND does not create a separate source-of-truth database

### Scenario: private content

- WHEN the dashboard shows AI usage
- THEN it does not display prompts, transcripts, code contents, or secrets by
  default
