# Spec: Moat Visualization Surface

## Requirement: Cost-by-client over time

The dashboard MUST render a stacked time series with USD on the value
axis and one band per client project (adrift its own labelled band),
over the selected range. It MUST NOT substitute tokens for dollars.

### Scenario: spend split by client
- GIVEN sessions for `acme:web`, `globex:ml`, and unattributed
- WHEN the moat surface renders
- THEN each appears as its own band; the adrift band is present and
  labelled (not silently dropped).

## Requirement: Attribution-confidence trend

A per-period stacked series MUST show counts by confidence band
(`timer`/`mapped`/`toml`/`auto`/`none`) using the v2.65
`attribution_confidence` mapping (legacy `git` → `auto`).

## Requirement: Per-project billable-evidence

For each client project the surface MUST show human time, AI cost,
session count, outcome split (shipped/in-flight/abandoned/no-PR from
`pr_state`), and the project's dominant attribution confidence. Human
time MUST be absent (not `0`) when no timeclock exists.

## Requirement: Leakage funnel proposes, never writes

Adrift sessions MUST be shown per remote with `$` and count and a
runnable `halyard link-repo … --remote …` command. Rendering MUST NOT
modify `repos.toml`, `halyard.toml`, or any log.

## Requirement: Moat stays primary

Moat panels (cost-by-client / billable-evidence) MUST render before
the v2.64 commodity stats panel in the default layout. A test MUST
assert this ordering.

### Scenario: ordering invariant
- WHEN the dashboard renders with both surfaces present
- THEN a moat panel precedes the commodity stats panel.

## Requirement: Trust preserved, offline, no new capture

Every dollar MUST keep its cost trust label; outcomes MUST be labelled
state, never an ROI/value claim. Rendering MUST be static server-side
SVG/HTML (no client-side charting, offline). No new session field or
capture path may be introduced.

## Requirement: Single remediation source

The `halyard link-repo` remediation string MUST come from one shared
builder used by both `doctor` and the leakage funnel (no divergent
copies).
