# v2.74 — Ambient Status: Tasks

Status: **COMPLETE 2026-05-17 (1286 tests passing)** — contract +
`status --snapshot`/`--watch` shipped. Menu-bar shim **deferred**
(Phase-0 gate, see below). Adopts CodexBar's surface lesson, not its
job; mission guardrails enforced as tests.

## Phase 0 (BLOCKING the menu-bar piece only)
- [x] Outcome: **deferred.** The macOS menu-bar shim requires a real
  launchd/PyObjC environment to validate; not verifiable in this
  build environment. Per the changeset gate the contract + terminal
  watch ship now; the shim is a later, separately-spiked addition.
  No `halyard[menubar]` extra added yet.

## Contract (reuse existing builders — audited)
- [x] `status_snapshot.py`: `StatusSnapshot` composed ONLY from
  existing builders — `aggregate_session_dirs`+`parse_sessions`+
  `_dedup_sessions` (same aggregator as dashboard/report),
  `sum_spend`, `summarize_ai_sessions` (by-client), doctor
  (`build_doctor_report`/`has_errors`), `budget_status`,
  `leakage`/`unattributed_log_count`. **Zero new captured fields.**
- [x] Projection: linear run-rate only; `estimate=True`
  non-removable; run-rate 0 / no-limit ⇒ `days_until_limit=None`;
  no divide-by-zero
- [x] Emitted via the v2.69 `jsonio` seam

## Renderers
- [x] `halyard status --snapshot` (one-shot, `--json` → snapshot
  contract) and `--watch [--interval N]` (redraw loop, Ctrl-C),
  stdlib only. v2.69 `status --json` timer contract **unchanged**
  (additive — regression-tested)
- [x] `status_render.render_status_text` pure fn; user strings
  markup-escaped (v2.38); `~` marks estimates
- [ ] macOS menu-bar shim — deferred (Phase 0)

## Guardrail tests (`tests/test_v274_ambient_status.py`, 11 cases)
- [x] single-source parity: `spend.month_usd == sum_spend(...)`
- [x] privacy: build opens no provider credential/cookie/keychain
  path (recording-`open` allowlist test)
- [x] projection math + `estimate` always true + zero-run-rate +
  no-limit
- [x] empty/no-budget/no-session clean state
- [x] render escapes markup + shows `~` estimate
- [x] v2.69 `status --json` timer shape preserved; `--snapshot
  --json` is the distinct new contract
- [x] tracing-aware perf bound on the per-build over 5k sessions
- [x] NEGATIVE guard: no provider quota/reset/incident/credential
  code introduced (privacy test + none written)

## Docs
- [x] PRD/ARD already written (no scope shift)
- [x] Roadmap entry + status/test count in `openspec/project.md`

## Decision gate
- [x] Contract built with **zero** new captured data — no field cut,
  none added. Menu-bar deferred, not forced.

## Gate
- [x] `pytest` green (1286 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
