# Proposal: v2.11 — Hook Normalization and Auto-Install

## Why

Halyard grew three separate hook-install commands with inconsistent names
(`install-hook`, `install-gemini-hook`, `install-cursor-hook`). The names were
hard to discover, and new users had no way to know which tools Halyard supports
or how to activate tracking for them.

Additionally, `halyard init` left hook installation as a manual step. This
meant that many users captured zero sessions even after a successful init
because they never ran the hook command.

## What changes

- Rename hook install commands to a consistent `install-hook-{tool}` pattern.
- Keep old names as hidden aliases so existing scripts do not break.
- Auto-detect `claude`, `cursor`, and `gemini` on PATH during `halyard init`
  and install hooks for any that are present.
- Report which tools were found and hooked, and which were not found, at the
  end of init output.

## What stays the same

- Hook files and installation targets are unchanged.
- Users can still install hooks manually after init.
- No new dependencies.

## Out of scope

- Hook removal / uninstall command.
- Detection of tools installed outside PATH (e.g. App Store).
- Windows support.

## Success criteria

- `halyard init` in a directory with `claude` on PATH installs the Claude Code
  hook without any additional steps.
- Old command names still work.
- `halyard install-hook-claude`, `halyard install-hook-cursor`, and
  `halyard install-hook-gemini` are the canonical names shown in `--help`.
