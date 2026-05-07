# Proposal: v2 — Local Activity Dashboard

## Why

The AI Work Ledger gives Halyard a powerful data foundation, but invisible
capture needs a visible local surface. Claude-mem's local dashboard is useful
because it shows what the background system is doing. Halyard needs the same
kind of view for human time, AI sessions, costs, attribution, and collector
health.

Users should not have to inspect `time.timeclock`, `ai-sessions.log`, and
configuration files manually just to know whether capture is working.

## What changes

Add a local dashboard started by:

```bash
halyard dashboard
```

The dashboard runs on localhost and reads the same plain-text project files as
the CLI. It shows:

- a modern Glass Cockpit overview for live AI work;
- active timer and current project;
- recent AI sessions;
- human hours and AI cost by project;
- model/tool mix;
- direct, allocated, inferred, and missing cost states;
- unattributed sessions needing review;
- collector health, including Claude Code hook status.

## What stays the same

- Files remain the source of truth.
- The CLI remains fully usable without the dashboard.
- No cloud account is required.
- No private prompt or code content is shown by default.
- Writes still require explicit approval.

## Out of scope

- Hosted team dashboard.
- Multi-user authentication.
- Background daemon required for normal CLI use.
- Prompt/code transcript capture.
- Replacing invoice generation or reports.

## Success criteria

- `halyard dashboard` starts a local server and prints a localhost URL.
- The Today view shows the active timer, recent sessions, and AI cost summary.
- The Glass Cockpit view feels modern, dense, and operational rather than like
  a generic SaaS landing page.
- The Health view shows whether Halyard can capture Claude Code sessions.
- The dashboard clearly surfaces unattributed AI sessions.
- The dashboard uses the same parsers and report calculations as the CLI.

## Product reference

See `docs/PRD-local-activity-dashboard.md`.
