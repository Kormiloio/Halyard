# Tasks: v3.12 — VS Code OpenTelemetry collector

## Phase 0 — spike (gate before any mapper code)

- [ ] Point VS Code at a throwaway local collector; run one Copilot agent
      session; capture a real OTLP/JSON payload.
- [ ] Confirm: exact GenAI attribute keys; whether `session.id` is a
      resource vs span attribute; token usage on spans vs metrics; the
      session-end / flush signal. Record findings in `design.md`.
- [ ] Decide tool slug (`github-copilot` reuse vs `vscode-copilot`) and
      `job_id` scheme; record the decision.

## Implementation (only after Phase 0)

- [ ] Span→`AiSession` mapper (`collectors/vscode_otel.py`): GenAI semconv →
      fields, per-`session.id` aggregation, `normalise_input`, model_breakdown,
      duration/TTFT → `api_seconds`. Pure function, unit-testable.
- [ ] Local OTLP/HTTP receiver on `127.0.0.1:4318` hosted in `halyard service`
      (no protobuf; OTLP/JSON via stdlib). TTL/end-of-session flush
      (Windsurf v3.6 pattern) → `append_session`.
- [ ] `install-vscode-otel` / `uninstall-vscode-otel` (diff-and-approve writes
      the three `github.copilot.chat.otel.*` keys, content capture off).
- [ ] Importer dedup coordination (skip OTel-captured sessions; document
      preference order).
- [ ] `doctor` nudge: Copilot on disk but OTel unwired (warning).

## Privacy (binding)

- [ ] Metadata allowlist in the mapper; everything else dropped.
- [ ] Fuzz/contract test: content-stuffed spans never reach row / log line /
      `--json`.
- [ ] Test: receiver binds localhost only.

## Tests / verification

- [ ] Mapper unit tests (single + multi-model, tool calls/errors, aggregation).
- [ ] Coexistence test: OTel row + importer → no double-count.
- [ ] ruff / mypy / full suite green.

## Docs

- [ ] `openspec/project.md` roadmap entry (item 66, v3.12).
- [ ] `docs/` setup note (enable OTel in VS Code → halyard receiver; the
      collector-file fallback).
- [ ] CHANGELOG.

## Related — SHIPPED as v3.13 (separate changeset)

- [x] `copilot.py` parser rewritten to reconstruct the incremental patch format
      (`kind:0` snapshot + `kind:1/2` key-path updates), fixing the silent skip.
      Was a format-drift fix, not the glob fix originally assumed. Regression
      test for the `["requests", N, "response"]` sub-path form.
- [x] v3.10 canary extended to `github-copilot` + `codex` (importer-aware
      coverage probe).
