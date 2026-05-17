# v2.74 — Ambient Status

> Spec only — proposed. Full rationale: [PRD](../../../docs/PRD-ambient-status.md)
> · [ARD](../../../docs/ARD-ambient-status.md). Prompted by a
> competitive read of CodexBar; adopts its *surface* lesson only, not
> its job.

## Why

Halyard's behavior-changing answers — *is capture healthy, what am I
spending, am I about to blow a client's budget* — are locked behind a
dashboard/CLI the user must open. They find out capture broke, or a
project overran, at invoice time. An ambient, never-opened surface
fixes that with data we already have.

## What changes

1. **Status contract.** Extend `halyard status` to emit one
   structured snapshot (via the v2.69 `jsonio` seam) built **only**
   from existing builders: capture health (`doctor`), today/month/
   by-top-client spend (`build_ai_report`/`sum_spend`), adrift count,
   and per-budget burn + linear projection (`budgets.toml` +
   month-to-date). No new captured field, no new file.
2. **`halyard status --watch`.** A compact self-refreshing one-screen
   terminal view (all platforms). The guaranteed deliverable.
3. **macOS menu-bar renderer (optional).** A thin shim over the same
   contract, delivered through the existing `halyard service` launchd
   agent. Spike-gated; degrades to `--watch` everywhere else.

## Explicit non-goals (mission guardrails — enforced in tasks)

- No provider quota / rate-limit / reset tracking.
- No provider breadth race (CodexBar's ~29) — depth-first stays.
- No provider status/incident polling.
- **No reading provider credentials, cookies, keychains, or API
  keys.** Reads only Halyard's own plain-text files. Non-negotiable.
- No new source of truth; no new captured data; no network bind.
- Projection is a labeled estimate, never presented as measured.

## Constraints honored

- **Single source of truth.** Every renderer consumes the one
  contract; numbers can't diverge from `report`/dashboard (same rule
  as v2.70 leverage, v2.71).
- **Local-first, plain-text, no secrets.** Pure reader.
- **Cross-platform core, optional native polish.** Terminal mode is
  the floor; menu bar is additive and gated.

## Phase 0 (blocking the menu-bar piece only)

A spike MUST prove the Python macOS menu-bar path (PyObjC/`rumps`
under launchd, optional `halyard[menubar]` extra) is robust enough to
ship. If not: defer the menu-bar renderer, ship the contract +
`--watch` anyway. The contract is the deliverable; the menu bar is a
bonus. (Lesson from v2.67: gate uncertain integrations behind a
verify-first spike.)
