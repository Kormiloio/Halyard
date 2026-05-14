# v2.33 — Hub-First Dashboard & Voyage Auto-Detection

## Problem

Two friction points make The Bridge misleading on first use:

1. **Wrong scope by default.** `halyard dashboard` opens in whatever directory the
   user runs it from. If a hub is configured, the user sees one project's data
   instead of their full AI work picture. The whole value proposition of Halyard
   is cross-tool, cross-project visibility — but the default view defeats that.

2. **Voyages require manual setup.** The Current Voyage panel shows "At anchor"
   for every project that lacks a `voyages.toml` entry, no matter how much work
   has been done. A developer who has run 74 sessions across a month sees "At
   anchor" because they never created a voyage record. That is both wrong and
   discouraging. If we force users to set up voyages manually, they will abandon
   the tool.

3. **Missing `time.timeclock` shows "Error".** The health panel treats a missing
   timeclock as a red error state. Human time tracking is optional; a missing
   timeclock means "not started", not "broken".

## Proposed changes

### 1. Hub-first dashboard scope

When `halyard dashboard` starts, resolve scope in this order:

1. If `--project <path>` is given, use that path.
2. If a hub is configured (`~/.halyard/hub` exists), use the hub directory.
3. Fall back to CWD (current behavior).

The header should show "hub" (or the hub directory name) rather than the
single-project name when hub scope is active. All stat cards, voyage panel,
and health checks run against the hub's aggregated session data.

This requires no new data formats — the hub already aggregates sessions from
registered projects. It just needs to be the default.

### 2. Voyage auto-detection from sessions data

The voyage stage is inferred automatically from the project's session history.
No `voyages.toml` entry is required to leave "At anchor".

Inferred stages:

| Stage | Condition |
|---|---|
| At anchor | No sessions recorded, OR hub not configured |
| Anchors Aweigh | 1+ sessions recorded |
| Making Headway | 10+ sessions, 50%+ attributed |
| Rounding the Mark | 30+ sessions, 70%+ attributed, any PR outcomes present |
| Flying Colors | 50+ sessions, 80%+ attributed, 1+ merged PR |
| Shipshape · Moored | Project marked complete in projects.toml OR manually closed |

If a `voyages.toml` entry exists, its explicit stage overrides the inferred
stage. Auto-inferred stages are labelled "auto" in the UI to distinguish them
from manually set stages.

The "⚓ At anchor" label changes to show the inferred stage name automatically
as data accumulates — no user action required.

### 3. Fix timeclock missing → "Error" bug

`_file_check` returns "error" for any missing file. Timeclock is optional.
Change `build_health_checks` to emit "neutral" (not "error") when
`time.timeclock` does not exist. The detail text: "not started — run
`halyard start` to begin tracking time."

This removes the spurious red "Error" pill from the dashboard header for any
project that uses Halyard for AI cost tracking only.

## What this is not

- This does not add new data formats.
- This does not require voyages.toml to exist.
- This does not change how sessions are captured or attributed.
- Explicit voyages.toml entries remain supported and override auto-detection.

## Success criteria

- `halyard dashboard` opened from any directory shows hub data if a hub is
  configured, without any flags.
- A project with 74 sessions shows a stage other than "At anchor" automatically.
- A project with no timeclock shows "Warning" or "neutral" health, not "Error".
- No new commands, no new config keys, no new data files required.
