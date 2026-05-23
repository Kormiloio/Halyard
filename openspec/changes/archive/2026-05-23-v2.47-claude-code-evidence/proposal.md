# v2.47 — Extend Evidence-Free Guard to Claude Code

## Problem

v2.46 added `collectors.session_has_evidence` and applied it to the
Gemini and Cursor stop handlers, but explicitly scoped Claude Code out
("not implicated in this report — revisit only if the same evidence-free
pattern is shown there").

It is now shown there. The project log is full of Claude Code rows like:

```
claude-code claude-unknown 0 0 0.0000 … tokens_available=false
  source=hook … telemetry_source=claude-code-hook
```

`handle_stop_hook` in `collectors/claude_code.py` builds and appends a
session on **every** Stop fire, even when transcript/token resolution
failed and there is no signal (unknown model, zero tokens, no
interactions, no tool calls, no code delta). The dashboard's "Recent AI
Sessions" / "captured" count is dominated by these `claude-unknown 0/0
$0` stubs, burying the real sessions (which carry a real model, tokens,
and interaction counts via the transcript path).

Same defect, same fix shape as v2.46 — just the third collector.

## Goals

- Apply the existing `session_has_evidence` predicate in
  `claude_code.handle_stop_hook` exactly as in Gemini/Cursor: a Stop
  fire with no evidence of a real turn is **not** written.
- Real Claude Code sessions (transcript-enriched: real model, tokens,
  interaction counts, tool calls, or code delta) are recorded exactly
  as before — no legitimate session dropped.

## Non-goals

- Changing `record_session_start`, the budget check, or the
  auto-timer/dashboard-hint side effects (they only matter for real
  sessions; skipping an empty fire skips them harmlessly).
- Re-pricing or backfilling already-logged stubs (operational cleanup,
  separate).
- Codex collector — not implicated; revisit only if shown.

## Out of scope

The reason the Stop hook often can't resolve tokens (transcript timing)
is a separate enrichment question; this change only stops the
*evidence-free* write, consistent with v2.46.
