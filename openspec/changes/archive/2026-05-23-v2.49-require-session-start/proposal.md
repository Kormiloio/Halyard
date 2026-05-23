# v2.49 — Cursor/Gemini Stop Requires a Recorded Session Start

## Problem

An external daemon (the `thedotmack` claude-mem
`worker-service.cjs --daemon`, PID observed live) fires the Cursor
`stop` and Gemini `AfterAgent` hooks every ~minute with canned
payloads (`cursor claude-3.5-sonnet 2000 400`,
`gemini-cli gemini-2.0-pro 100 50`, constant `wall_seconds=1800`).
These carry nonzero tokens + a real model and a plausible <12h span,
so neither the v2.46 evidence guard nor the v2.48 implausibility guard
catches them — they keep landing in the hub as unattributed
("Sessions Adrift") work the user never did.

The tell: **no `~/.halyard/cursor-session` / `gc-session` state file
exists** when these fire. The real hook lifecycle is two-phase —
`beforeSubmitPrompt`→`record_session_start` (writes the state file),
then `stop`→`handle_stop_hook` (reads + clears it). The daemon only
triggers the *stop* phase, so there is no recorded start. A stop with
no recorded start is, by definition, not a real turn.

## Goal

Cursor `handle_stop_hook` and Gemini `handle_agent_stop` MUST refuse to
record a session when their session-start state file is absent. Real
usage always records a start first, so no legitimate session is lost;
stop-only synthetic fires produce nothing.

## Non-goals

- Claude Code is unaffected (real lifecycle + already guarded by the
  v2.47 evidence check; not the synthetic target).
- Distinguishing synthetic-but-fully-lifecycled payloads (out of
  Halyard's reach; not what's happening here).
- Managing the external daemon — that's the user's tool; this change
  makes Halyard correct regardless of it.

## Out of scope

Re-cleaning the already-written synthetic rows (operational, with
backups) and advising on the daemon are handled alongside, not in code.
