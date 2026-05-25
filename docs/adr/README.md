# Architecture Decision Records

Short, durable records of cross-cutting decisions that outlive any single
changeset. Per-version *implementation* design lives in
`openspec/changes/<version>/design.md`; ADRs capture the decisions that span
many versions and that reviews keep re-litigating.

Format: one file per decision, `NNNN-kebab-title.md`, numbered in order.
Status is one of `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-timezone-model.md) | Timezone model: naive-local domain time, UTC for machine logs | Accepted |
