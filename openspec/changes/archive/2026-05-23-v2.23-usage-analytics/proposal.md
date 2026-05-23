# Proposal: v2.23 - Usage Analytics

## Why

Halyard has a strong ledger and operational dashboard, but its current views
are more useful than delightful. Individual AI tools now show attractive
session analytics: summary cards, active-day grids, model share charts, peak
hours, and streaks. Those views are not just pretty; they help users understand
their own AI work patterns quickly.

Halyard can do this better because it captures across tools and projects.
Usage Analytics adds a stats-forward layer over the existing local ledger
without weakening Halyard's privacy, billing, or audit model.

## What changes

Add a Usage Analytics surface backed by shared aggregation services.

The feature provides:

- overview metrics for sessions, tokens, active days, streaks, peak hour, and
  favorite model;
- all-time, 30-day, and 7-day ranges;
- an activity heatmap;
- daily model usage charts;
- model and tool share breakdowns;
- missing-data states for unavailable tokens, costs, or interaction counts;
- a dashboard Usage view and a CLI/JSON summary entry point.

## What stays the same

- `ai-sessions.log` remains the source of truth.
- Existing report and dashboard calculations continue to work.
- The Glass Cockpit remains the operational capture and billing readiness view.
- No prompt, transcript, code, or secret content is displayed.
- No cloud account or hosted service is required.

## Out of scope

- Hosted team analytics.
- Productivity scores or developer ranking.
- Prompt or transcript analytics.
- Replacing invoices, budgets, or cost allocation.
- Perfect normalization across tools that expose different telemetry.

## Success criteria

- The Usage view renders from local ledger data with no network dependency.
- A user can switch between all-time, 30-day, and 7-day ranges.
- Overview shows sessions, total tokens, active days, streaks, peak hour, and
  favorite model.
- Models shows daily usage and aggregate model share.
- Missing token or cost data is visible and not treated as zero.
- Tests cover aggregation, ranges, streaks, heatmap buckets, and model share.

## Product reference

See `docs/PRD-usage-analytics.md`.

