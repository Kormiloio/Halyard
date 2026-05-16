# Spec: TUI ↔ web dashboard parity

## Requirement: Moat information parity in the TUI

The TUI MUST surface the web dashboard's moat story: cost-by-client,
attribution-confidence mix, leakage rows with the exact one-command
fix, and per-project billable evidence — reusing `moat.cost_by_client`,
`moat.leakage`, `attribution.attribution_confidence`, and the existing
report/human-time builders. No new captured data.

### Scenario: moat pane content
- GIVEN sessions across two clients with one unattributed remote
- THEN the moat pane text shows each client's spend, the
  attribution-confidence mix, and the adrift remote with its
  `halyard link-repo …` fix (proposed, not run).

## Requirement: Outcomes/leverage parity

The TUI MUST surface the "did it ship?" leverage answer (shipped %
and merged/open/none buckets) equivalent to the web Leverage panel.

## Requirement: Single source of truth for leverage

The leverage % + bucket math MUST be a shared function consumed by
both the web `_leverage_panel` and the TUI pane. The two surfaces
MUST NOT compute it independently.

### Scenario: surfaces agree
- GIVEN one session set
- THEN the web panel and the TUI pane report identical leverage
  numbers (from the shared `leverage.summarize`).

## Requirement: Testable without the Pilot harness

The new panes MUST expose their rendered output as text
(`last_rendered_text`, the v2.64 `UsagePane` pattern) so correctness
is unit-tested in the covered layer. This change MUST NOT require the
Textual `Pilot`/`run_test()` harness.

## Requirement: Trust + injection safety preserved

Attribution-confidence and cost trust labels MUST render in the TUI
panes (not flattened). All model/remote/client/text interpolated into
panes MUST be escaped (`rich.markup.escape`) per the v2.38 markup
-injection invariant.

## Requirement: Recorded policy lift

`openspec/project.md` "Deferred or gated" MUST record that v2.70
lifts the TUI-deferral for these parity panes by explicit owner
decision (generalising the v2.64 carve-out). The Pilot-harness
deferral for untouched widgets stands.
