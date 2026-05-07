# Cost Center Spec

## Requirement: project-level cost center mapping

The org admin dashboard MUST support mapping projects to cost centers for
finance reporting and chargeback.

### Scenario: cost_center in projects.toml

- WHEN a project in `projects.toml` has a `cost_center` field
- THEN the finance export uses that cost center code for sessions attributed
  to the project

### Scenario: org-level cost center override

- WHEN `org-cost-centers.toml` exists at the hub root
- THEN it maps project slugs or team slugs to cost center codes
- AND the project-level `cost_center` field takes precedence over team-level
  mappings if both are defined

### Scenario: unattributed sessions in finance export

- WHEN a session has no project attribution
- THEN it appears under "(unattributed)" in the finance export
- AND is not silently assigned to any cost center

### Scenario: session with inferred attribution

- WHEN a session's project was inferred from timeclock overlap
- THEN the finance export labels its cost center allocation as "inferred"
- AND does not present it as a confirmed cost

---

## `org-cost-centers.toml` Schema

```toml
# Maps project slugs to cost center codes.
# Team-level entries apply to all projects under that team
# unless the project has its own entry.

[[project_mapping]]
project_slug = "acme:auth"
cost_center = "CC-ENG-0042"

[[project_mapping]]
project_slug = "acme:dash"
cost_center = "CC-ENG-0043"

[[team_mapping]]
team_id = "auth-team"
cost_center = "CC-ENG-0040"   # fallback if no project entry matches
```

---

## Requirement: finance export

The org admin dashboard MUST export cost allocation data in a format
consumable by BI and accounting systems.

### Scenario: CSV cost allocation export

- WHEN finance exports a billing period
- THEN the CSV includes one row per project-team-cost-center combination with:
  - billing_period (YYYY-MM)
  - cost_center
  - team_id
  - project_id
  - tool
  - sessions
  - direct_usd (captured/calculated costs)
  - allocated_usd (seat/credit plan costs)
  - total_usd
  - trust (captured / allocated / mixed)
- AND the export is deterministic for the same input data

### Scenario: mixed-trust finance total

- WHEN a cost center total contains both captured and allocated amounts
- THEN the export marks the row trust as "mixed"
- AND shows direct_usd and allocated_usd as separate columns
