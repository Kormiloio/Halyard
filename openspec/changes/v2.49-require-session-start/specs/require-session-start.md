# Spec — Cursor/Gemini stop requires a recorded session start

## Requirement: Cursor stop needs a session-start state

WHEN the Cursor `stop` hook fires AND `~/.halyard/cursor-session` does
not exist
THEN `handle_stop_hook` MUST NOT record (or write-unattributed) a
session and MUST return 0.
WHEN the file exists (a real `beforeSubmitPrompt` ran)
THEN behaviour is unchanged (evidence + implausibility guards still
apply).

## Requirement: Gemini AfterAgent needs a session-start state

WHEN the Gemini `AfterAgent` hook fires AND `~/.halyard/gc-session`
does not exist (no `SessionStart` ran)
THEN `handle_agent_stop` MUST NOT record a session and MUST return 0.
WHEN the state exists
THEN behaviour is unchanged.

## Requirement: No legitimate session is dropped

Real Cursor/Gemini turns always record their start first; this change
MUST only suppress stop/AfterAgent fires that have no recorded start.
Claude Code MUST be unaffected.
