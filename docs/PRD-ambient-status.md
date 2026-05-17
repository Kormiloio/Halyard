# PRD: Ambient Status (v2.74)

**Status — 2026-05-17:** Proposed. Spec-only; no code until reviewed.
Prompted by a competitive read of CodexBar (menu-bar AI-limit app).

## Summary

Halyard's value — *is my AI work being captured, what is it costing
me per client, am I near budget* — is currently locked behind a
dashboard or CLI you must deliberately open. Ambient Status surfaces
the three answers that change behavior **without the user opening
anything**: capture health, spend (today / month / by top client),
and budget burn with a projection.

## Why now

A competitive read of [CodexBar](https://github.com/steipete/CodexBar)
(a ~12k-star macOS menu-bar app for AI provider *limits*) makes one
thing clear: the most behavior-changing surface is the one that is
always visible and never opened. Halyard has the data (hooks, ledger,
budgets, doctor) but no ambient surface. This PRD adopts the *surface
lesson* — not CodexBar's job.

## What we deliberately do NOT build (mission guardrails)

These are CodexBar's domain; taking them would dilute Halyard's
system-of-record / billing-proof identity:

- **Provider quota / rate-limit / reset-window tracking.** Halyard is
  backward-looking proof, not a quota watcher. If a user needs "when
  does my Claude window reset," CodexBar exists and is better.
- **Breadth for breadth's sake (CodexBar tracks ~29 providers).**
  Halyard stays depth-first: hook-captured, attribution-rich, fewer
  tools done properly.
- **Provider status / incident polling.** Ops tooling, not our job.
- **Storing provider credentials, cookies, or API keys** to read
  provider dashboards. This violates Halyard's no-secret-capture,
  plain-text-local stance. Non-negotiable.

## The Halyard-native reframe of CodexBar's headline value

CodexBar: *"when does my provider quota reset — should I start a long
task?"* Halyard's on-mission analog uses data we already capture:

> **Budget burn:** at the current spend rate, you will hit the
> monthly budget *you set* for `client:project` on ~the 23rd;
> projected month-end spend is $X vs your $Y limit.

Forward-looking and plan-enabling like CodexBar — but about the
user's own business budget (existing `budgets.toml`), not a
provider's rate limit. No new captured data; this is projection over
the existing ledger + budgets.

## Users & job-to-be-done

- **Freelancer/agency (primary):** "Tell me, without my asking, if
  capture breaks or if a client project is about to blow its budget —
  because I only find out at invoice time today."
- **Solo dev:** "Glance: is Halyard actually capturing, and what have
  I spent today?"

## Scope (MVP)

1. **A stable status contract** — one structured snapshot
   (`halyard status` extended) reusing existing builders
   (doctor/report/budget): capture health (hooks present, minutes
   since last capture), today/month spend, adrift count, and
   per-budget burn + projection.
2. **Terminal ambient mode** — `halyard status --watch`: a compact,
   self-refreshing one-screen view (works on macOS/Linux/Windows).
3. **macOS menu-bar renderer (optional, additive)** — a thin shim
   over the same contract, delivered through the existing
   `halyard service` launchd path. macOS-only; everything degrades to
   the terminal mode elsewhere.

## Non-goals

- A second source of truth or any new captured field.
- Cross-platform native GUIs (Windows/Linux tray) in MVP.
- Replacing the dashboard/TUI — this is the *ambient* glance; the
  dashboard remains the deep surface.
- Notifications/alerting beyond a visible state change in MVP
  (push/email is a later, gated follow-up).

## Success

- A user can tell capture is healthy or broken **without opening
  anything**, within 2 seconds of looking.
- Budget overruns are seen *before* invoice time, not at it.
- Zero new data files; zero credentials stored; the status contract
  is the same numbers the CLI/dashboard already report (single
  source of truth).

## Open questions (resolved in the ARD)

- Native Swift app vs. reuse the Python service? → ARD.
- What exactly is in the status contract, and is it really
  derivable with no new capture? → ARD + spec design.
