# v2.60 — Claude Code Collector Enrichment

## Problem

Claude Code is the user's primary tool (≈80% of tokens — Sonnet 4.6 +
Opus 4.7), yet it is Halyard's **weakest collector**. `AiSession`
already models `session_id`, `tool_calls`, `tool_errors`,
`wall_seconds`, `user_message_count`, `accepted_suggestion_count`, and
`model_breakdown`, but `collectors/claude_code.py` populates only
`assistant_message_count`, `cache_read`, and `cache_write`.

The Claude Code `Stop` hook payload exposes session id, turn/tool
activity, and timing. We are discarding it. The consequence: for the
tool that generates most of the work, Halyard's per-session record is
materially thinner than what the user already sees in Claude Code's
own end-of-session summary — the exact "I already get this from my AI
tool" dismissal risk.

## Goal

Populate every rich `AiSession` field Claude Code's hook payload makes
available, with the project's "unavailable is not zero" semantics
(absent → `None`, never a fabricated `0`).

Target fields (capture only what the payload actually provides):

- `session_id` — Claude Code's native session UUID
- `tool_calls` / `tool_errors`
- `wall_seconds` — session wall duration from the payload
- `user_message_count` (assistant already captured)
- `accepted_suggestion_count` — if exposed by the payload
- `model_breakdown` — when a session spans multiple models/subagents
  (full treatment is v2.61; v2.60 wires it for Claude Code where the
  payload already carries per-model usage)

## Constraints honored

- **Unavailable is not zero.** A field absent from the payload stays
  `None`; the v2.32 metadata-parity semantics are not weakened.
- **No new schema.** Every field already exists on `AiSession`; this
  is collector-population only — bug-class enrichment, not a feature.
- **Privacy boundary unchanged.** Counts and ids only — never prompt,
  code, or transcript content.
- **Backward compatible.** Old log lines without these fields parse
  exactly as before; new lines add key=value tokens already understood
  by the parser.

## Non-goals

- Multi-model cost-split semantics (v2.61).
- Cache-pricing correctness (v2.62).
- Time decomposition beyond `wall_seconds` (v2.63).

## Out of scope

Reverse-engineering Claude Code internals beyond the documented Stop
hook payload. If a field isn't in the payload, it stays `None` and the
v2.59 drift canary will surface a regression if a previously-populated
field disappears.
