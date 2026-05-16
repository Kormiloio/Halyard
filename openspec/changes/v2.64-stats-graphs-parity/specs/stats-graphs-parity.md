# Spec: Stats & Graphs Parity Surface

## Requirement: Table-stakes parity

The dashboard MUST present, at minimum, the stat set a single-tool
dashboard shows: sessions, messages, total tokens, active days,
current streak, longest streak, peak hour, favorite model — plus a
contribution heatmap and a per-day per-model token chart with an
input/output split and per-model % share.

### Scenario: headline cards
- GIVEN a populated ledger
- WHEN the dashboard renders
- THEN all eight headline figures are present with correct values
  from `UsageAnalytics` (+ the new `total_messages`).

### Scenario: heatmap
- GIVEN activity across N days in the selected range
- THEN a calendar grid renders one cell per day with intensity
  bucketed by that day's activity, plus a legend.

### Scenario: model time series
- GIVEN multi-day, multi-model usage
- THEN a stacked per-day chart renders one segment per model; per-day
  segments sum to that day's total; the legend shows per-model in/out
  and % share summing to ~100%.

## Requirement: Message aggregate

`UsageAnalytics` MUST expose `total_messages` and
`message_data_missing_sessions`, mirroring the existing
token-missing-count pattern (absent per-session counts are not faked
as 0).

## Requirement: Moat stays primary

The parity surface MUST be additive. Cost and project/attribution
panels MUST remain present and not be removed or demoted to make room.

### Scenario: moat-protection regression
- WHEN the dashboard renders with the new surface
- THEN the cost panel and project attribution are still present.

## Requirement: Trust + offline preserved

Every figure MUST keep its trust label; rendering MUST be static
server-side SVG/HTML with no client-side charting dependency (offline,
zero-build). Any flavour/comparison line MUST be clearly
non-authoritative and MUST NOT appear on reports or invoices.

## Requirement: TUI information parity

The TUI MUST surface the headline figures (sessions, messages,
tokens, active days, streaks, peak hour, favorite model). Graphical
heatmap/stacked chart are not required in the TUI.
