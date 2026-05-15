# Trust Aggregates Spec

## Requirement: aggregate trust labels

The org admin dashboard MUST preserve cost quality information when aggregating
session data across users, teams, and time periods.

### Scenario: all-captured aggregate

- WHEN all sessions in an aggregate have `trust = captured`
- THEN the aggregate trust label is `captured`

### Scenario: mixed-trust aggregate

- WHEN an aggregate contains sessions with different trust labels
- THEN the aggregate trust label is `mixed`
- AND the breakdown shows how much of the total is captured, allocated, and
  inferred

### Scenario: partially missing aggregate

- WHEN some sessions in a team or project have no cost data (`cost_usd = 0`
  and no plan allocation)
- THEN the aggregate flags those sessions as `missing` cost
- AND the total is marked `mixed` rather than showing a false-precision total

### Scenario: inferred attribution in aggregate

- WHEN a team aggregate includes sessions with inferred project attribution
- THEN the aggregate shows an inferred session count alongside the total
- AND finance reports label inferred cost separately

---

## Requirement: aggregate display rules

### Scenario: aggregate dashboard total

- WHEN a dashboard widget shows a total AI cost for a team or org
- THEN it renders as: `$X.XX (captured $A, allocated $B)`
  when the aggregate is mixed
- OR simply `$X.XX` when all components share the same trust label

### Scenario: consistent cost arithmetic

- WHEN org, team, project, people, and finance aggregates are built from the
  same sessions
- THEN each aggregate uses the same direct/allocated/total cost arithmetic
- AND credit or seat sessions are not counted in some views but omitted from
  others
- AND the aggregate total equals direct cost plus allocated cost for every view

### Scenario: unknown cost sessions excluded from totals

- WHEN sessions have `trust = missing` (no captured cost and no plan allocation)
- THEN the dashboard shows session count separately from the cost total
- AND does not add zero to the total as if the cost were zero
- AND surfaces the count as a governance gap

---

## Trust Label Definitions for Aggregates

| Label | Meaning in an aggregate |
|---|---|
| `captured` | All contributing sessions have directly recorded cost |
| `calculated` | All costs derived from captured tokens and pricing table |
| `allocated` | All costs are seat/credit plan estimates |
| `inferred` | Attribution (not cost) was inferred for one or more sessions |
| `missing` | One or more sessions have no cost figure (seat with no plan configured) |
| `mixed` | Two or more different trust types contribute to the total |

`inferred` applies to attribution quality, not cost quality. A session can be
both `captured` (cost) and `inferred` (attribution). The dashboard surfaces
both dimensions independently.
