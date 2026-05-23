# Tasks: v3.12 — VS Code OpenTelemetry collector

## Phase 0 — spike (gate before any mapper code)

- [~] **DEFERRED (no live capture possible).** The GitHub Copilot Chat
      extension is not installed in the build environment (only
      third-party `namdang.ollama-copilot-vscode` + `github.codespaces`),
      so a live Copilot agent session could not be run to capture a real
      OTLP/JSON payload. Owner approved building now against the
      *documented* GenAI semconv + OTLP/JSON encoding, with the live
      verification deferred. See design.md "Phase 0 (deferred)".
- [~] Confirm exact GenAI attribute keys / placement — **deferred**; the
      mapper instead probes both placements defensively (resource *and*
      span `session.id`; tokens harvested wherever they appear on spans;
      metrics endpoint accepted but not parsed). Re-verify against a live
      capture before production reliance.
- [x] Tool slug + `job_id` scheme decided: reuse `tool="github-copilot"`
      (existing report/dashboard bucket) with `telemetry_source="copilot-otel"`
      to distinguish from the importer's `copilot-jsonl`; `job_id=copilot-otel:<session.id>`.

## Implementation (only after Phase 0)

- [x] Span→`AiSession` mapper (`collectors/vscode_otel.py`): GenAI semconv →
      fields, per-`session.id` aggregation, `normalise_input`, model_breakdown,
      duration → `api_seconds`/`tool_seconds`. Pure function, unit-testable.
- [x] Local OTLP/HTTP receiver on `127.0.0.1:4318` (`collectors/otel_receiver.py`),
      started from `run_dashboard` **only when opted in** (no protobuf; OTLP/JSON
      via stdlib). Idle-TTL + shutdown flush (Windsurf v3.6 pattern) → `append_session`.
- [x] `install-vscode-otel` / `uninstall-vscode-otel` (diff-and-approve writes
      the three `github.copilot.chat.otel.*` keys, content capture off; opt-in marker).
- [x] Importer dedup coordination (skip OTel-captured sessions via dedup-state
      fast path + authoritative ledger `job_id` scan; OTel wins, importer fills gaps).
- [x] `doctor` nudge: Copilot on disk but OTel unwired (warning, never error).

## Privacy (binding)

- [x] Metadata allowlist in the mapper; everything else dropped (never looked up).
- [x] Fuzz/contract test: content-stuffed spans never reach row / log line /
      `--json` (asdict) surface.
- [x] Test: receiver binds localhost only (`server_address[0] == 127.0.0.1`).

## Tests / verification

- [x] Mapper unit tests (single + multi-model, tool calls/errors, aggregation,
      span-attr session id, malformed-input tolerance, value decoding).
- [x] Coexistence test: OTel row + importer → no double-count (state file + ledger + e2e).
- [x] ruff / mypy / full suite green (1432 tests).

## Docs

- [x] `openspec/project.md` roadmap entry (v3.12).
- [x] `docs/` setup note (enable OTel in VS Code → halyard receiver; the
      collector-file fallback).
- [x] CHANGELOG.

## Related — SHIPPED as v3.13 (separate changeset)

- [x] `copilot.py` parser rewritten to reconstruct the incremental patch format
      (`kind:0` snapshot + `kind:1/2` key-path updates), fixing the silent skip.
      Was a format-drift fix, not the glob fix originally assumed. Regression
      test for the `["requests", N, "response"]` sub-path form.
- [x] v3.10 canary extended to `github-copilot` + `codex` (importer-aware
      coverage probe).
