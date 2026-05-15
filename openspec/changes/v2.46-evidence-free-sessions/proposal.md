# v2.46 — Suppress Evidence-Free Collector Sessions

## Problem

`gemini_cli.handle_agent_stop()` and `cursor.handle_stop_hook()`
**unconditionally** build and append an `s` session whenever the
stop/AfterAgent hook fires — even when nothing happened that turn: no
tokens, no history file, no tool calls, no interactions, no code delta,
no model. The result is a ledger full of zero-signal rows.

This is the in-Halyard root cause of the "phantom Cursor / repeating
Gemini" pollution the user hit: the Cursor `beforeSubmitPrompt`/`stop`
chain (and other vendors sharing that hook array) fires the collector
without a real Cursor turn, and every fire writes a session. v2.45
stopped the *duplication*; this stops a single spurious fire from
becoming a ledger row at all.

Note (honest scope): the constant `cursor 2000/400` and
`gemini 100/50` token values originate from **external/synthetic hook
payloads**, not a Halyard default — Halyard cannot tell a synthetic
"100/50" payload from a real tiny turn. This change does not try to.
It removes the class Halyard *does* control: **emitting a session when
there is no evidence a turn occurred at all.**

## Goals

- A collector stop hook that fires with **zero evidence of a real
  turn** MUST NOT append a session (and MUST still clear its state).
- "Evidence" = any of: tokens present, a parsed history summary
  (gemini), tool calls/errors, interaction data, code delta, or commit
  count.
- Real but cheap turns (any tokens, or any tool/interaction/code
  signal) are still recorded — no legitimate session is dropped.
- Symmetric guard in both the Gemini and Cursor collectors (same defect,
  same symptom).

## Non-goals

- Filtering nonzero-but-synthetic payloads (Halyard can't distinguish
  them; out of scope and would risk dropping real data).
- Changing SessionStart state-writing or the 12-hour stale guard.
- Pruning the user's already-polluted log (separate, operational,
  pending explicit confirmation).

## Out of scope

Codex / Claude Code collectors — not implicated in this report and
their hooks fire on genuine session boundaries; revisit only if the
same evidence-free pattern is shown there.
