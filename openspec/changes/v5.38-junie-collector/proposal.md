# v5.38 — Junie was captured by nothing at all

## Why

The user said, in passing, that they had used Junie. Halyard had no
collector for it, no doctor check, and no mention of it anywhere in the
codebase. Four sessions and **23,148,120 tokens** had accumulated on disk,
entirely unrecorded.

It went unnoticed because Junie is not only the JetBrains IDE plugin — it
ships as a standalone CLI at `~/.local/bin/junie`, with state under
`~/.junie`. Nothing appears beneath
`~/Library/Application Support/JetBrains`, so the usual signal that a
JetBrains tool is installed is absent. The first search for it found
nothing and looked conclusive.

That is the uncomfortable part: every capture gap this track has found was
discovered by someone noticing a number looked wrong. This one had no
number to look wrong, because the tool produced no rows at all. The
`unwired.*` nudges exist precisely to catch that, and Junie was not among
the tools they knew to look for.

## What the data offers

Junie's on-disk layout is unusually good for capture:

- `~/.junie/sessions/index.jsonl` — one line per session with `sessionId`,
  `createdAt`/`updatedAt` (epoch ms), **`projectDir`**, and `taskName`.
- `~/.junie/sessions/<id>/events.jsonl` — events whose
  `event.agentEvent.kind == "LlmResponseMetadataEvent"` carry a
  `modelUsage` list of `{model, cost, inputTokens, outputTokens,
  cacheInputTokens, cacheCreateTokens}`.

`projectDir` is a better attribution signal than Codex offers, which
records only a working directory.

## What

- **`collectors/junie.py`** — an importer, not a live hook: Junie writes
  continuously, so a session is re-imported as its `events.jsonl` grows,
  using the size-keyed state introduced for Codex in v5.2.
- **`halyard import-junie`**, folded into `import-all`.
- **`unwired.junie`** doctor check — history on disk, nothing imported.

Verified against the real machine: 4 sessions, 23,148,120 tokens, matching
a raw independent count of the same files exactly.

## Two judgement calls

**Local models are recorded, not billed.** All observed usage was
`Qwen3.6-27B-MLX-4bit` — on-device inference, genuinely `$0.00`. Those rows
carry `billing="local"`, so the tokens count toward usage while the spend
stays out of money totals (`sum_spend` already filters on
`billing == "api"`). The classification is gated on model-name markers
rather than `cost == 0.0`, so a *hosted* model reporting zero — a free
tier, a billing outage — is not silently reclassified and dropped from
spend.

**The 12 h plausibility cap is deliberately not applied.** The first
version used `session_is_implausible` and dropped 2 of the 4 sessions,
including the 75 h one the user had specifically asked about. Junie holds a
session open across days (143 h and 75 h observed) and dropping them loses
their tokens entirely. That cap guards *duration* reporting, which v5.33
and v5.35 already bound at the right layer by excluding over-cap sessions
from timeclock reconciliation and the coverage denominator. Recording the
row and bounding what it may claim beats discarding the work.

## Out of scope

- **Attribution.** All four sessions import unattributed: `projectDir`
  points at `~/Development/kormilo`, a parent directory rather than a
  repository, so `infer_project` finds no remote. This is the same
  path-versus-remote gap that leaves Codex's Mycelium session
  unattributed, and it deserves one fix covering both rather than a
  Junie-specific workaround.
- A live hook. Junie exposes no session-end hook; the importer is the
  available mechanism, as with Codex and Copilot.
