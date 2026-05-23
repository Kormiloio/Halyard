# v2.43 — Actionable Health Warnings

## Problem

The dashboard topbar shows a status pill ("Healthy" / "Warning" /
"Error"). When it says "Warning" the user has no way to learn *what* is
wrong or *where to get fix instructions* from the dashboard:

- The pill is a bare element — no tooltip, not clickable, no link to
  detail.
- The failing detail only appears in the small Collector State / Health
  panel far down the page.

Note: the dashboard's `HealthCheck` (built in `reports.py`) carries only
`label/status/detail` — it has **no** per-check `fix` field (that is a
separate `DoctorCheck` type used by the `halyard doctor` CLI). So this
change does not invent per-check remediation text; it surfaces the real
detail prominently and points the user to `halyard doctor`, where full
diagnostics and fixes already live.

## Goals

- Make the topbar status pill informative: a native `title` summary on
  hover, and clickable to open a popup listing every non-healthy check
  with its detail.
- The popup points the user to `halyard doctor` for full diagnostics
  and remediation (the authoritative source) rather than fabricating
  per-check fix text the dashboard data does not have.

## Approach

Server-rendered. The popup's contents are emitted in the page (hidden)
from the same `state.health` list; a small fail-safe script only toggles
its visibility and handles Esc / outside-click / close. This keeps the
recently-hardened dashboard's client surface minimal and the content
accessible without JS-built DOM.

## Non-goals

- No new health checks or changes to `doctor` logic.
- No server endpoint or state — display only.
- No change to the pill's healthy/warning/error coloring.

## Out of scope

Auto-running fixes from the dashboard. The popup shows the command/steps;
the user runs them (consistent with "no silent writes").
