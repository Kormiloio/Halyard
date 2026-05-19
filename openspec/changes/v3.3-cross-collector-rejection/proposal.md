# Proposal (feasibility-gated): v3.3 — Cross-collector rejection capture

**Status: PROPOSAL ONLY — not approved for design/specs/tasks.** This
document is the read-only Phase-0 feasibility note requested before
committing to the work. It ends with a per-collector go/no-go and a
recommendation. No `design.md`/`specs/`/`tasks.md` until the open
decision below is made.

## Why this exists

v3.2 surfaced rejections but only Cursor *captures* them — its payload
hands Halyard `accepted/rejectedSuggestionCount` pre-computed. The
v3.2 honest-labelling infra ("rejections: not captured" for the other
tools) is correct but the gap is real: a Claude-Code-heavy user gets no
rejection signal at all. This note establishes whether closing that gap
is even possible per collector, *before* a changeset is written.

## Phase-0 findings (read-only audit, 2026-05-18)

Inspected each collector's actual data source:

| Collector | Source | Accept/reject analogue present? | Verdict |
|---|---|---|---|
| **Cursor** | structured payload with `acceptedSuggestionCount` / `rejectedSuggestionCount` | Yes — pre-computed by Cursor | **Done** (v3.2) |
| **Claude Code** | Stop-hook → `transcript_path` JSONL (`tool_use` / `tool_result`, `is_error`) | **Partial / entangled.** A user-denied tool-use appears as a `tool_result` with `is_error: true` — i.e. it is *already counted inside v3.2's `tool_errors`*. The signal exists in the transcript but is conflated with genuine tool failures | **Feasible, but needs a v3.2 reconciliation decision** |
| **Codex** | rollout event log (`event_msg` typed events) | **Plausible, unconfirmed.** Codex has an approval mechanism (exec / apply-patch approve-or-deny). The current parser only handles a subset of `msg_type`; approval-decision events are not parsed today. Needs a 1-file event-schema spike to confirm the decision is recorded | **Feasible pending a small spike** |
| **Gemini CLI** | parsed history session file (`HistorySummary`: tokens + tool_errors only) | **Absent.** No inline accept/reject UX; the history file has no such concept | **Not feasible — N/A by tool design** |

## The load-bearing finding (Claude Code ⟂ v3.2)

This is the reason this is not a quick add. For Claude Code, a
"rejection" *is* a user denying a tool-use — and v3.2's `tool_errors`
already counts every `is_error` `tool_result`, which **includes** those
denials. So adding a Claude Code rejection signal is not additive; it
**reinterprets a subset of an already-shipped signal**. Three options,
and this is the decision that gates the changeset:

1. **Rejections are a disjoint reclassification of tool_errors.** A
   denied tool-use counts as a rejection, *not* a tool error.
   Pro: semantically cleanest. Con: changes v3.2 `tool_errors`
   numbers for Claude Code users (a shipped, surfaced metric moves).
2. **Rejections are an overlapping sub-count.** `tool_errors` stays
   as-is; rejections are a separate count that happens to overlap.
   Pro: no v3.2 regression. Con: a user adding `tool_errors` +
   `rejections` double-counts the same events — needs explicit
   "(overlaps tool_errors)" labelling, more honest-labelling infra.
3. **Don't derive Claude Code rejections from `is_error` at all** —
   require a distinct transcript marker (if Claude Code emits one for
   user-denied permission vs. tool failure). Pro: no overlap, no
   reclassification. Con: depends on a transcript field that may not
   exist; needs its own spike.

Until the owner picks 1/2/3, a Claude Code changeset cannot be
specified — every downstream surface and the v2.32 trust labelling
hinges on it.

## Per-collector recommendation

- **Gemini CLI → close as N/A, permanently.** Not "deferred pending
  work" — the signal does not exist in the tool. v3.2's "not captured"
  label is the correct permanent end state. Document and stop.
- **Codex → small standalone changeset, gated on a 1-file spike**
  (confirm the rollout log records approve/deny decisions and their
  schema). If the spike passes, this is a clean additive parse in
  `codex_app.py` with no v3.2 entanglement. Highest value-to-risk.
- **Claude Code → its own changeset, blocked on the option-1/2/3
  decision above.** Do not start until that is made; it touches a
  shipped metric.

## Recommendation

Do **not** pursue "cross-collector rejection" as one epic. Split:

1. Mark Gemini N/A now (doc-only, no code).
2. Spike Codex's event schema (≤1 file, read-only) → if green, a small
   `v3.3-codex-rejection` changeset.
3. Defer Claude Code until the owner answers the v2.32-reconciliation
   question (option 1/2/3). It is the highest-value collector but the
   only one that perturbs already-shipped v3.2 numbers.

Tradeoff: this deepens the rejection signal unevenly and, for Claude
Code, partially *reinterprets* v3.2 `tool_errors` — which is precisely
why v3.0 deferred it and why it should not be rushed into one change.

## Decision required (owner)

- [ ] Accept "Gemini = N/A permanent".
- [ ] Approve a read-only Codex event-schema spike.
- [ ] Pick option 1, 2, or 3 for Claude Code rejection vs. v3.2
  `tool_errors` — or explicitly defer Claude Code.

No further v3.3 artifacts (design/specs/tasks) will be written until
the above is decided.
