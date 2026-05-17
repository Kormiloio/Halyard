# v2.74 — Ambient Status: Tasks

Status: **proposed (spec only, not started).** Adopts CodexBar's
surface lesson, not its job. Mission guardrails are enforced as
tasks, not just prose.

## Phase 0 (BLOCKING the menu-bar piece only)
- [ ] Spike: Python macOS menu-bar under launchd
  (PyObjC/`rumps`, optional `halyard[menubar]` extra) — robust to
  ship? Record outcome: proceed / defer-menubar-ship-contract-only

## Contract (must reuse existing builders — audit first)
- [ ] Audit + cite the existing function for every `StatusSnapshot`
  field (doctor/report/sum_spend/leakage/budgets). Any field needing
  **new capture is cut**, not added — record what (if anything) was cut
- [ ] `StatusSnapshot` + `status --json` via the v2.69 `jsonio` seam
- [ ] Projection: linear run-rate only; `estimate: true` non-removable;
  run-rate 0 ⇒ `days_until_limit=None`
- [ ] Per-tick read uses the SQLite cache / trailing window, not a
  full re-parse

## Renderers
- [ ] `halyard status --watch` (`--interval`, default 30 s) — all
  platforms, stdlib only, the guaranteed deliverable
- [ ] macOS menu-bar shim **iff Phase 0 passed**: `halyard menubar`
  entry point, `halyard[menubar]` extra, launchd-targetable via the
  existing `halyard service`; no socket bound

## Guardrail tests (mission enforcement)
- [ ] single-source parity: snapshot values == `report`/`budget`/
  `doctor` outputs
- [ ] privacy: snapshot path opens only Halyard files — never provider
  creds/keychain/cookies (allowlist/import audit test)
- [ ] projection math + `estimate` always true + no divide-by-zero
- [ ] `--watch` single-frame render (no infinite loop); tracing-aware
  perf bound (`perf_ceiling` fixture) over a large log
- [ ] empty/no-budget/no-session clean states
- [ ] NEGATIVE guard: a test/grep asserts no provider-quota / reset /
  incident / credential code was introduced

## Docs
- [ ] PRD/ARD already written; update them only if scope shifts
- [ ] Roadmap entry + status/test count in `openspec/project.md`

## Decision gate
- [ ] Contract not buildable without new captured data ⇒ reduce scope
  to existing data or shelve — never add capture to satisfy this
  feature. Record the decision.

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
