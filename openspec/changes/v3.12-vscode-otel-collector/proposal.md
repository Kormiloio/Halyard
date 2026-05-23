# Proposal: v3.12 — VS Code OpenTelemetry collector (Copilot capture)

## Why this exists

Copilot capture (v3.7) works by **scraping VS Code's undocumented internal
storage** (`workspaceStorage/<ws>/GitHub.copilot-chat/chatSessions/*.jsonl`).
That is the same fragility class that broke Gemini for 16 days — and it has
**already broken again, observed live (2026-05-23):** a Copilot code review
produced session `27738553-…` on disk, but VS Code moved chat sessions up a
level — from `…/GitHub.copilot-chat/chatSessions/` to
`workspaceStorage/<ws>/chatSessions/`. The importer's glob no longer matches,
so `halyard import-copilot` silently reported "no new sessions" and the review
was **never captured**. (Worse: the v3.10 coverage canary doesn't probe
importer tools, so nothing flagged it — see Related findings.)

Meanwhile, VS Code 1.119+ now emits **standard OpenTelemetry** for agent
sessions under the GenAI semantic conventions — token usage, operations, chat
sessions, tool calls, and per-model latency/TTFT — exportable to any local OTLP
endpoint (verified: `github.copilot.chat.otel.enabled` +
`github.copilot.chat.otel.otlpEndpoint: http://localhost:4318`, off by
default). This is a **documented, stable, opt-in** capture source that does not
break when Microsoft reshuffles internal files.

## What changes

- **A local OTel ingestion path for VS Code Copilot.** Halyard receives the
  OTLP stream on localhost and maps GenAI-semconv spans/metrics to `AiSession`
  rows — live, standards-based capture that replaces the brittle file scrape.
- **Setup**: `halyard install-vscode-otel` writes the three
  `github.copilot.chat.otel.*` settings (diff-and-approve, like the hook
  installers) pointing VS Code at Halyard's local receiver; `halyard doctor`
  nudges if Copilot is on disk but OTel isn't wired.
- **The v3.7 importer stays as a fallback** until OTel capture is proven, and
  is dedup-coordinated so the two paths never double-count the same session.
- **Privacy is the binding constraint** (non-negotiable #5): ingest *metadata
  only* — token counts, model, tool-call counts, durations, session id. GenAI
  spans can carry prompt/response content if content-capture is enabled;
  Halyard never reads, stores, or forwards any content attribute.

## Out of scope

- The Azure Managed Grafana / ops dashboard — that's infra-team performance
  observability (cloud-required, Copilot-only). Halyard's lane is the local,
  cross-tool, $/attribution/outcome ledger. We consume the same OTel *source*;
  we do not rebuild their dashboard.
- OTel ingestion for tools other than VS Code Copilot (Gemini already has its
  own outfile path in v2.67; a general OTel receiver is a possible later
  generalization, noted in design, not built here).
- Capturing prompt/response content (explicitly forbidden).

## Related findings (this investigation) — both now SHIPPED as v3.13

1. **Importer parser format-drift (fixed).** The miss was *not* a path/glob
   issue (the importer already reads the current `workspaceStorage/<ws>/
   chatSessions/` location). VS Code changed the *session file format* to an
   incremental patch log — a kind-0 snapshot plus `kind:1`/`kind:2` updates at
   a key path. The model output now arrives via `["requests", N, "response"]`
   sub-path patches; the old parser only handled a whole-array `["requests"]`
   replace, so every recent session looked empty and was skipped. Fix:
   reconstruct the final state from the patches, then count. (Same drift class
   as Gemini — and the reason OTel is worth it: this *will* keep happening.)
2. **Coverage-canary gap (fixed).** v3.10 probed only `claude-code` and
   `gemini-cli`, so it didn't catch this. Extended to `github-copilot` and
   `codex` (on-disk session newer than last import → warning).

Both landed in v3.13 so capture is restored today; v3.12 (this proposal) is the
durable replacement that stops the format-drift cycle entirely.

## Success criteria

- With OTel enabled, a Copilot agent session in VS Code produces an `AiSession`
  row live (no manual import), with model, tokens, tool-call count, and
  duration/TTFT, attributed to the workspace's project.
- A fuzz test proves no prompt/response content can reach the ledger or any
  `--json` surface.
- The path survives an internal-storage layout change (it doesn't read internal
  storage at all).
- ruff/mypy/tests green; coexists with the importer without double-counting.
