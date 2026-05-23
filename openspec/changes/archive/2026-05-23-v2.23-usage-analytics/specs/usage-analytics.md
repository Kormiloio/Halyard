# Usage Analytics Spec

## Requirement: usage analytics service

Halyard MUST provide a shared usage analytics aggregation service over parsed AI
sessions.

### Scenario: aggregate usage summary

- WHEN the service receives parsed sessions
- THEN it returns total sessions, input tokens, output tokens, cache tokens,
  cost, active days, streaks, peak hour, favorite model, model buckets, tool
  buckets, and daily buckets
- AND the result is independent of any specific renderer

### Scenario: empty data set

- WHEN the service receives no sessions
- THEN it returns zero totals
- AND active days is `0`
- AND current streak is `0`
- AND longest streak is `0`
- AND peak hour is absent
- AND favorite model is absent

### Scenario: reuse parser semantics

- WHEN sessions are read from `ai-sessions.log`
- THEN usage analytics uses the existing Halyard session parser
- AND applies supported amendment records the same way existing reports do

## Requirement: time ranges

Usage Analytics MUST support all-time, 30-day, and 7-day ranges.

### Scenario: all-time range

- WHEN the selected range is `all`
- THEN every parsed session is included

### Scenario: 30-day range

- WHEN the selected range is `30d`
- THEN sessions whose local start date falls within the last 30 days including
  the range end date are included
- AND older sessions are excluded

### Scenario: 7-day range

- WHEN the selected range is `7d`
- THEN sessions whose local start date falls within the last 7 days including
  the range end date are included
- AND older sessions are excluded

### Scenario: deterministic testing

- WHEN callers pass a fixed `now`
- THEN range boundaries, active days, streaks, and peak hour are calculated
  relative to that fixed value

## Requirement: overview metrics

Usage Analytics MUST expose overview metrics for at-a-glance interpretation.

### Scenario: active days

- WHEN sessions exist on distinct local dates
- THEN active days equals the number of distinct local dates with at least one
  session in the selected range

### Scenario: current streak

- WHEN sessions exist on consecutive local dates ending on the range end date
- THEN current streak equals the length of that consecutive run

### Scenario: current streak with no end-date activity

- WHEN no session exists on the range end date
- THEN current streak is `0`

### Scenario: longest streak

- WHEN sessions exist on multiple runs of consecutive local dates
- THEN longest streak equals the length of the longest run in the selected
  range

### Scenario: peak hour

- WHEN multiple sessions have local start times
- THEN peak hour is the hour with the highest session count
- AND ties choose the earliest hour

### Scenario: favorite model by tokens

- WHEN token data is available
- THEN favorite model is the model with the highest total token count

### Scenario: favorite model fallback

- WHEN no token data is available for any model
- THEN favorite model is the model with the highest session count

## Requirement: daily activity

Usage Analytics MUST expose day-level activity data suitable for a heatmap.

### Scenario: build day buckets

- WHEN a range is selected
- THEN the service returns one bucket per local date in that range
- AND each bucket includes session count, token totals, cost, missing-token
  status, and model breakdown

### Scenario: inactive day

- WHEN no sessions exist on a day inside the selected range
- THEN that day bucket has zero sessions and zero available totals
- AND is distinguishable from a day with sessions but missing token data

### Scenario: unavailable token data

- WHEN a session has `tokens_available=false`
- THEN it contributes to session count and active-day calculations
- AND increments missing-token metadata
- AND its token count is not treated as known zero usage

## Requirement: model analytics

Usage Analytics MUST expose model-level usage breakdowns.

### Scenario: model bucket totals

- WHEN sessions include multiple models
- THEN each model bucket includes sessions, input tokens, output tokens, cache
  tokens, cost, token share, cost share, and session share

### Scenario: share percentages

- WHEN total usage for a share metric is greater than zero
- THEN model shares are calculated relative to that total

### Scenario: zero denominator

- WHEN total usage for a share metric is zero
- THEN share values are `0`
- AND rendering code does not divide by zero

### Scenario: unknown model labels

- WHEN sessions contain unknown or default model labels
- THEN those labels appear as captured
- AND are not silently discarded

## Requirement: tool analytics

Usage Analytics MUST expose tool-level usage breakdowns.

### Scenario: tool bucket totals

- WHEN sessions include multiple tools
- THEN each tool bucket includes sessions, total available tokens, cost, and
  session share

### Scenario: unknown tool labels

- WHEN sessions contain unknown tool labels
- THEN those labels appear as captured
- AND are not silently discarded

## Requirement: dashboard usage view

The local dashboard MUST include a Usage Analytics view.

### Scenario: open Usage view

- WHEN the user opens the local dashboard Usage view
- THEN the view shows Overview and Models tabs
- AND shows a range control for all-time, 30-day, and 7-day ranges

### Scenario: overview tab

- WHEN the Overview tab renders
- THEN it shows summary cards, an activity heatmap, tool share, and warnings
  for unattributed or missing-token sessions when present

### Scenario: models tab

- WHEN the Models tab renders
- THEN it shows daily model usage and aggregate model breakdowns

### Scenario: no sessions

- WHEN no sessions exist in the selected range
- THEN the Usage view renders an empty state
- AND does not crash or show misleading chart values

## Requirement: CLI usage command

Halyard SHOULD provide a CLI summary for usage analytics.

### Scenario: text summary

- WHEN the user runs `halyard usage`
- THEN Halyard prints overview metrics for the default range

### Scenario: selected range

- WHEN the user runs `halyard usage --range 7d`
- THEN Halyard prints metrics for the 7-day range

### Scenario: JSON summary

- WHEN the user runs `halyard usage --json`
- THEN Halyard emits machine-readable JSON based on the shared usage view model

## Requirement: privacy and local-first behavior

Usage Analytics MUST preserve Halyard's privacy model.

### Scenario: metadata only

- WHEN usage analytics renders session data
- THEN it displays metadata such as time, tool, model, tokens, cost, project,
  branch, attribution state, and operational telemetry
- AND it does not display prompts, transcripts, source code, file contents, API
  keys, or secrets

### Scenario: local data source

- WHEN usage analytics renders
- THEN it reads local Halyard project files and selected local Halyard state
  only
- AND it does not require a network connection or cloud account

