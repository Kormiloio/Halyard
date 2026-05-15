# v2.10 Guided Setup

## Summary

Add `halyard setup`, a guided onboarding command that reduces hook installation
friction for new users.

`halyard doctor` tells users what is wrong. `halyard setup` should help them get
to a healthy state with fewer decisions.

## Motivation

Current setup requires users to understand which AI tools need which command:

```bash
halyard install-hook
halyard install-cursor-hook
halyard install-gemini-hook
```

That is fine for technical users but creates friction for anyone who just wants
Halyard to capture their first AI session.

The desired first-run flow is:

```bash
halyard init
halyard setup
halyard doctor --first-capture
```

## Goals

- Add a single command for guided setup.
- Detect project and hub readiness.
- Install selected hooks through one command.
- Support non-interactive usage through flags.
- Run a doctor-style readiness summary after setup.
- Keep the existing individual hook install commands for advanced/manual use.

## Non-Goals

- Do not auto-install hooks without explicit flags or confirmation.
- Do not remove or rewrite existing third-party hook configuration.
- Do not require network access.
- Do not capture any AI prompt, transcript, or source code content.
- Do not replace `halyard doctor`.

## User Stories

- As a new user, I can run `halyard setup --all --yes` and install supported
  hooks in one command.
- As a Claude Code user, I can run `halyard setup --claude --yes` without
  learning the lower-level command name.
- As a user outside a project, I get clear guidance to run `halyard init` or set
  a hub before expecting capture to work.
- As a maintainer, I can still point advanced users to the existing specific
  hook installers.

