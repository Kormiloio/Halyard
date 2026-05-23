# Proposal: v3.6 — Windsurf Collector

## Why this exists

Windsurf (by Codeium) is a rapidly growing AI-native IDE. While Halyard
supports VS Code via manual task capture, Windsurf's deeper agentic
capabilities (Cascades) produce high-volume AI activity that should be
captured autonomously.

A Phase-0 research spike (2026-05-22) confirmed that Windsurf exposes a
native hook surface at `~/.codeium/windsurf/hooks.json`. This allows
Halyard to implement a native collector that captures session timing,
model usage, and interaction metadata without manual user intervention.

## What changes

- **New Collector:** `src/halyard/collectors/windsurf.py`.
- **Hook Integration:** `halyard install-windsurf-hook` command to
  register Halyard in `~/.codeium/windsurf/hooks.json`.
- **Session Capture:** Use `pre_user_prompt` to trigger session start and
  `post_cascade_response` to trigger session record (similar to Claude
  Code's stop hook).
- **Metadata Support:** Attempt to extract token counts, model names, and
  interaction metrics from the Windsurf hook payloads (pending spike).
- **Roadmap:** Item 59 in `openspec/project.md`.

## User Stories

- **As a Windsurf user**, I want my Cascade sessions to be automatically
  logged to `ai-sessions.log` so I don't have to manually record them.
- **As a developer**, I want to see which Windsurf models I'm using most
  and how they contribute to my total AI spend.

## Success Criteria

- `halyard setup --all` or `halyard setup --windsurf` installs the hooks.
- Starting a Cascade in Windsurf creates a Halyard session.
- Ending or completing a Cascade records the session with tokens and
  cost.
- Zero impact on Windsurf performance (hooks run with short timeouts).

## Out of Scope

- Manual "record-session" for Windsurf (already covered by generic CLI).
- Capturing non-Cascade autocomplete events (too high volume/noise).

## Risks and Trade-offs

- **Hook Stability:** The `hooks.json` interface is relatively new and
  undocumented; it may change in future Windsurf versions.
- **Payload Schema:** We don't yet know the exact schema of the JSON
  payloads Windsurf passes to hooks.
- **Privacy:** As with all collectors, we must ensure we only capture
  metadata and never prompt or code content.
