# Spec — Claude Code evidence-free guard

## Requirement: No Claude Code session without evidence

WHEN the Claude Code Stop hook fires AND there is no evidence of a real
turn — unknown model, zero tokens, no interaction/assistant counts, no
tool calls, no code delta, no commit (i.e. `session_has_evidence` is
False)
THEN `handle_stop_hook` MUST NOT append (or write-unattributed) a
session, and MUST return 0.

## Requirement: Real Claude Code sessions are never dropped

WHEN a Stop fire carries any evidence — a real model, tokens, an
interaction or assistant-message count, tool calls, or code delta
(typically the transcript-enriched path,
`telemetry_source=claude-code-transcript`)
THEN the session MUST be recorded exactly as before, including
legitimate cheap turns with zero tokens but real interaction counts.

## Requirement: Shared predicate, consistent with v2.46

The check MUST use the same `collectors.session_has_evidence` predicate
applied to Gemini and Cursor in v2.46; no Claude-Code-specific
re-implementation.
