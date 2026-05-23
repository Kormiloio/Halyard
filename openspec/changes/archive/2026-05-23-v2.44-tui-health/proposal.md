# v2.44 — TUI Health Visibility

## Problem

v2.43 gave the **web** dashboard an actionable health surface (pill
tooltip + detail popup). The **TUI** (`halyard tui`) has no health
surface at all: it never renders the `build_health_checks` results, so a
terminal user has no way to know a collector/file check is failing —
not even a warning indicator, let alone the detail.

This is the same gap v2.43 closed on the web, on the other primary
surface.

## Goals

- Show a compact health indicator in the TUI status bar when any check
  is `warning`/`error` (and nothing when all healthy).
- A keypress opens a modal listing each failing check (label, status,
  detail) plus a line directing the user to `halyard doctor` for full
  diagnostics and fixes — mirroring the web popup.

## Approach

Reuse `reports.build_health_checks(project_dir)` — the same authoritative
data the web dashboard uses. No new data file, **no persistence**, no
new command. The modal mirrors the existing `HelpModal` pattern; the
indicator is appended to the existing `_status_text()`.

This is deliberately the *small* TUI investment: parity on the v2.43
value (know what's wrong + where to fix it), not the web's persistent
layout customization (which would need a TUI config file — explicitly
out of scope).

## Non-goals

- Persistent TUI layout / collapse / reorder.
- New or changed health checks.
- Auto-remediation (consistent with "no silent writes").

## Out of scope

Surfacing per-check fix text — the dashboard's `HealthCheck` has no
`fix` field (same finding as v2.43); the modal points to `halyard
doctor` instead of fabricating guidance.
