# Spec: Multi-Model Session Attribution

## Requirement: Per-model usage encoding

`model_breakdown` MAY carry per-model usage as
`model:in/out/cr/cw` segments joined by `|`. A legacy `model:count`
segment (no `/`) MUST still parse. Absent token ⇒ single-model.

## Requirement: Cost is the sum of per-model costs

When a usage-form breakdown is present, session cost MUST equal the
sum of `calculate_cost` over each segment. Otherwise cost MUST be
identical to the pre-change single-model computation.

### Scenario: 3-model session
- GIVEN a session with flash-lite + flash-preview + pro-preview usage
- THEN cost = cost(flash-lite seg) + cost(flash-preview seg) +
  cost(pro-preview seg), each via the pricing table.

### Scenario: no breakdown
- GIVEN a session with no `model_breakdown`
- THEN cost and all rollups are byte-identical to current behaviour.

## Requirement: Primary model

`session.model` MUST be the segment with the greatest cost share
(tie: token volume, then name), so one-line summaries and existing
consumers remain meaningful.

## Requirement: Correct per-model rollups

`usage` model buckets, `mcp_server.cost_by_model`, and the dashboard
model table MUST attribute tokens and cost per model from the
breakdown when present.

### Scenario: rollup attribution
- GIVEN one 3-model session
- WHEN `cost_by_model` is computed
- THEN three model rows appear with their own token/cost, not one row
  carrying the whole session.

## Requirement: Backward compatibility & round-trip

Existing logs (no breakdown, or count-form breakdown) MUST parse and
cost unchanged. A freshly written usage-form line MUST round-trip via
`parse_sessions`. No new `AiSession` field; no format change beyond
the generalised token grammar.
