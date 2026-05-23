# Proposal: v3.3 — Cross-collector rejection capture

Status: **shipped.**

## Why this exists

v3.2 surfaced rejections but only Cursor *captures* them — its payload
hands Halyard `accepted/rejectedSuggestionCount` pre-computed. The
v3.2 honest-labelling infra ("rejections: not captured" for the other
tools) is correct but the gap is real: a Claude-Code-heavy user gets no
rejection signal at all. This changeset closes the gap where
technically feasible.

## Findings and Decisions

Following the Phase-0 feasibility note (2026-05-22):

### 1. Gemini CLI → N/A (Permanently)
Gemini CLI has no inline accept/reject UX and the history file does not
track this concept. v3.2's "not captured" label is the correct and
permanent end state. This collector is excluded from further v3.3 work.

### 2. Codex → Additive Capture
Codex rollout logs (`rollout-*.jsonl`) contain `exec_command_end` and
`apply_patch_end` events. While these are currently counted as
`tool_errors` on failure, a 1-file event-schema spike is required to
confirm if a distinct `user_denied` status or `msg_type` exists for
rejected prompts. If confirmed, this is a clean additive parse.

### 3. Claude Code → Overlapping Capture (Option 2)
In Claude Code, a user-denied tool-use appears as a `tool_result` with
`is_error: true`.
- **Decision:** Use **Option 2 (Overlap)**. `tool_errors` remains the
  raw count of all `is_error` blocks. `rejections` will be a subset of
  those same blocks that match a "denied" marker (to be confirmed by
  spike).
- **Rationale:** Preserves historical `tool_errors` metrics while
  providing deeper visibility into why errors occurred. Dashboards will
  use "(overlaps tool_errors)" labelling to avoid misinterpretation.

## Risks and tradeoffs
