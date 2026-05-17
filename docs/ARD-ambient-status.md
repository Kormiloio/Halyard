# ARD: Ambient Status (v2.74)

**Status — 2026-05-17:** Proposed. Architecture decisions for the
[Ambient Status PRD](PRD-ambient-status.md).

## Context

We want an always-visible "is capture healthy / what am I spending /
budget burn" surface (CodexBar's surface lesson) without betraying
Halyard's principles: local-first, plain-text source of truth, no
stored secrets, cross-platform CLI core, single source of truth for
numbers.

## Decision 1 — Do NOT build a separate native (Swift) app

CodexBar is a Swift macOS app. Mirroring that would mean a second
codebase, a second render of every number, a new build/sign/notarize
toolchain, macOS-only, and drift between what the app shows and what
`halyard report` shows.

**Decision:** the feature is a **status contract + renderers**, not an
app. Python stays the single implementation. Rejected: native Swift
app (maintenance + duplication + drift cost outweighs UX polish for a
billing tool whose deep surface is already the dashboard/TUI).

## Decision 2 — One contract, reuse existing builders (no new data)

The status snapshot MUST be derived entirely from existing builders:

- capture health ← `doctor` checks (hook presence, last-capture
  recency) — already computed.
- spend today/month/by-client ← `build_ai_report` / `sum_spend` —
  already computed.
- adrift count ← existing unattributed/leakage path.
- budget burn + projection ← existing `budgets.toml` + month-to-date
  spend; projection = simple linear run-rate
  (`mtd_spend / day_of_month * days_in_month`) plus
  `days_until_limit = (limit - mtd) / daily_run_rate`. No model, no
  new field, explicitly labeled an estimate (trust discipline).

**Decision:** `halyard status` is extended to emit this as the **one**
structured object (JSON via the v2.69 `jsonio` seam). Every renderer
consumes that object. This is the same single-source-of-truth rule
used for v2.70 leverage and v2.71 — numbers can never disagree across
surfaces. Rejected: bespoke queries per renderer (drift risk).

## Decision 3 — Renderers, in priority order

1. **`halyard status --watch`** (all platforms) — redraw the snapshot
   on an interval; pure terminal, no deps. This is the MVP and the
   floor every platform gets.
2. **macOS menu-bar shim** (optional, additive) — a minimal status
   item that polls the same `status --json` and renders title +
   dropdown. Delivered via the **existing `halyard service` launchd
   agent** (v2.12), not a new daemon. Implementation candidates:
   `rumps`/PyObjC (stay in Python, optional extra
   `halyard[menubar]`), evaluated in a Phase-0 spike. If the Python
   menu-bar path proves fragile, the shim is deferred and the
   terminal watch mode still ships — the contract is the deliverable,
   the menu bar is a bonus.
3. Windows/Linux tray — explicitly out of scope for MVP (contract
   makes it possible later for a contributor).

**Decision:** ship the contract + terminal watch unconditionally;
menu-bar is gated on the spike and degrades gracefully.

## Decision 4 — Security / privacy invariants (non-negotiable)

- Reads only Halyard's own plain-text files + existing builders.
  **Never** reads provider cookies, keychains, or API keys (the
  explicit line vs. CodexBar's session-reuse model).
- No new file written; `--watch` and the shim are pure readers.
- The macOS shim binds nothing to the network; it shells/imports the
  same in-process builders the CLI uses. (It does NOT depend on the
  HTTP dashboard being up.)
- Projection is labeled an estimate everywhere it appears (no
  pretending a run-rate is a measurement — v2.40/trust discipline).

## Decision 5 — Performance

`status --watch` and the menu-bar poll must not re-parse the whole
log per tick at scale. Reuse the SQLite read-model cache where the
builders already do; the poll interval default is 30 s (configurable),
not sub-second. A trailing-window read, not a full re-aggregate, per
tick.

## Risks

- **Menu-bar shim fragility** (PyObjC/rumps packaging, launchd UX) —
  mitigated by making it optional and spike-gated; terminal mode is
  the guaranteed deliverable.
- **Projection misleading users** — mitigated by explicit estimate
  labeling and using the simplest defensible run-rate (no
  false-precision forecasting).
- **Scope creep toward CodexBar** — mitigated by the PRD's hard
  non-goals; the spec's tasks must not add provider/quota anything.

## Summary of decisions

| # | Decision |
|---|---|
| 1 | No separate native app — contract + renderers in Python |
| 2 | One status contract from existing builders; zero new data |
| 3 | Terminal `--watch` ships always; macOS menu-bar optional/spike-gated |
| 4 | Reads only Halyard's own files; never provider secrets; estimates labeled |
| 5 | Cache-backed, 30 s poll, trailing-window reads |
