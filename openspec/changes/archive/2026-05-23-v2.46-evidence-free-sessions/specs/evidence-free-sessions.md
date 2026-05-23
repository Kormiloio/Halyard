# Spec — Evidence-free collector sessions

## Requirement: No session without evidence of a turn

WHEN the Gemini AfterAgent hook or the Cursor stop hook fires AND there
is no evidence a real turn occurred — i.e. ALL of: no tokens (input,
output, cache all zero), no parsed history summary, no tool calls or
errors, no interaction counts, no code delta / files touched, no commit
count, and no identified model (empty or the `*-unknown` sentinel)
THEN the collector MUST NOT append (or write-unattributed) a session
AND MUST still clear/reset its hook state
AND MUST exit successfully (return 0).

## Requirement: Real turns are never dropped

WHEN any single evidence signal is present (tokens, history, tool
calls/errors, any interaction count, code delta, files touched, commit
count, or a real model name)
THEN the session MUST be recorded exactly as before (including
legitimate `tokens_available=false` sessions that still carry other
signals).

## Requirement: Symmetric across implicated collectors

The guard MUST be applied identically in both the Gemini and Cursor
stop handlers. Codex and Claude Code collectors are unchanged.

## Requirement: Honest scope

This MUST NOT attempt to classify nonzero-but-synthetic payloads as
fake; it only suppresses the wholly-empty fire. Documentation MUST state
that constant synthetic token values originate from external hook
payloads, not a Halyard default.
