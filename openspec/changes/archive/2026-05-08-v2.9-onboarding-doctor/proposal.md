# v2.9 Onboarding Doctor

## Summary

Add an onboarding and diagnostics layer that helps new users install Halyard,
verify local capture, and understand why a session was not recorded.

The center of the change is `halyard doctor`: a local-only diagnostic command
that checks project state, hub state, log health, hook installation, collector
state, and first-capture readiness.

## Motivation

Halyard's collectors and local ledger are now capable enough for early users,
but install and capture confidence remain the biggest launch risk.

Today a user can run several setup commands:

```bash
halyard init
halyard install-hook
halyard install-cursor-hook
halyard install-gemini-hook
halyard dashboard
halyard tui
```

But they do not have one obvious place to answer:

- Is this directory a Halyard project?
- Is the hub configured?
- Is `ai-sessions.log` present and writable?
- Are my hooks installed?
- Are sessions being captured?
- Did something land in `~/.halyard/unattributed.log`?
- Did malformed records go to quarantine?
- What should I do next?

The product needs to make invisible capture legible before asking users to trust
reports, invoices, dashboards, or enterprise rollups.

## Goals

- Add `halyard doctor` as the primary setup and diagnostics command.
- Report local project, hub, log, hook, and collector health.
- Explain actionable fixes in plain language.
- Support `--json` output for issue reports and future automation.
- Add a first-capture verification flow.
- Document common setup and capture failures in `docs/troubleshooting.md`.

## Non-Goals

- Do not capture prompts, transcripts, or source code.
- Do not require network access or a cloud account.
- Do not install hooks automatically without explicit user action.
- Do not block AI tools from running when diagnostics fail.
- Do not replace Glass Cockpit or the TUI.

## User Stories

- As a new user, I can run `halyard doctor` after installing hooks and know
  whether capture is ready.
- As a user who just finished an AI session, I can run `halyard doctor
  --first-capture` and know whether Halyard saw it.
- As a user whose session did not appear in the dashboard, I can see whether it
  was unattributed, quarantined, or never captured.
- As a maintainer, I can ask a user for `halyard doctor --json` output without
  asking them to share prompt or code content.

## Success Criteria

- A user can diagnose a missing first capture without reading source code.
- `halyard doctor` exits 0 when capture is healthy.
- `halyard doctor` exits non-zero when required project/log/hook checks fail.
- `halyard doctor --json` returns a stable schema suitable for bug reports.
- Troubleshooting docs cover the top setup failures for Claude Code, Cursor,
  Gemini CLI, hubs, unattributed sessions, and quarantine.

