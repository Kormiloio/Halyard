# Proposal: v2.3 — Gemini History Enrichment

## Why this change

The current Gemini CLI collector works by accumulating token counts across AfterModel
hook firings and finalising the record at AfterAgent. This produces one session record
per agent turn, with a cost calculated against a single model name.

Two problems:

1. **Multi-model cost inaccuracy.** A single Gemini session often uses multiple models —
   a cheap router/summarizer (`gemini-2.5-flash-lite`) alongside the main reasoning model
   (`gemini-3-flash-preview`) and occasional escalations to a pro model
   (`gemini-3.1-pro-preview`). Attributing the full token cost to one model name produces
   wrong numbers. Cost must be summed per model.

2. **No retroactive coverage.** The AfterAgent hook only fires while the hook is installed
   and Gemini is running. Sessions from before installation, or where the hook missed the
   shutdown event, are never captured.

Gemini CLI writes a complete session record to
`~/.gemini/tmp/{project-slug}/chats/session-{ISO-timestamp}-{session-id-prefix}.json`
for every session. Each message in that file contains per-call token counts, model name,
tool call history with pass/fail status, and thinking tokens. Everything in the shutdown
summary is derivable from this file.

## What this change does

### 1. Hook enrichment via history file lookup

`handle_agent_stop()` currently uses the cumulative token state accumulated by
`record_model_usage()`. After this change, it additionally looks up the history JSON
for the current `session_id`, reads the per-message breakdown, and uses it to:

- Compute cost accurately across all models used in the session.
- Record total tool call count and success count as tags.
- Use the model responsible for the most output tokens as the canonical `model` field.

The hook-accumulated state remains the fallback when the history file is not found.

### 2. `halyard import-gemini`

A new CLI command that scans all `~/.gemini/tmp/*/chats/session-*.json` files,
identifies sessions not already in any known project's log (by `session_id`), and
imports them. This provides:

- Retroactive coverage of all past Gemini sessions.
- Recovery when the hook missed a shutdown event.
- A one-time migration path for users who install Halyard after using Gemini CLI.

## What this change does NOT do

- No prompt content capture. Only metadata (tokens, models, costs, tool names, timing).
- No modification of existing log lines — import is append-only.
- No automatic background scanning. The user runs `halyard import-gemini` explicitly.
- No per-tool-call detail in the log. Aggregate counts only.

## Key decisions

**Why read the history file at hook time rather than only at import?**
The hook fires at the moment the session closes — the history file is guaranteed to exist
and be complete at that point. Reading it then produces accurate real-time records without
requiring a separate import step. Import remains for retroactive coverage.

**Why use the history file rather than expanding the hook state machine?**
The history file is the ground truth Gemini CLI itself uses to display the shutdown
summary. Deriving our numbers from the same source guarantees our figures match what
the user sees. Expanding the hook state machine to track per-model counts would
re-implement what the history file already contains.

**Why `model` = highest-output-token model?**
Output tokens are the primary cost driver and represent where the substantive reasoning
happened. The router/summarizer sub-agents consume relatively few tokens and should not
inflate the `model` field with a cheap model name that misrepresents the session's cost
tier.

## Success criteria

- A multi-model Gemini session produces a `cost_usd` that matches the sum of per-model
  costs, not a single-model approximation.
- `halyard import-gemini` imports all past sessions not already in the log, with accurate
  costs and model attribution.
- Re-running `halyard import-gemini` is safe — no duplicate records.
- Tool call count and success rate are visible as tags on each imported session.
