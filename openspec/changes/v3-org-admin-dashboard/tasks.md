# Tasks

Implementation checklist for v3 — Org Admin Dashboard.

## 1. Product foundation

- [x] 1.1 Write org admin dashboard PRD.
- [x] 1.2 Define manager, director, CIO, and finance users.
- [x] 1.3 Define org identity and team mapping model.
- [x] 1.4 Define cost center mapping model.

## 2. Org data contract

- [x] 2.1 Define normalized org event schema.
- [x] 2.2 Preserve local `ai-sessions.log` semantics in sync.
- [x] 2.3 Define trust labels for aggregates.
- [x] 2.4 Define privacy boundary and excluded content.

## 3. Dashboard views

- [x] 3.1 Executive overview (`halyard org` — org-level summary with trust).
- [x] 3.2 Team rollups (per-team sessions, cost, active users, unattributed count).
- [x] 3.3 Project rollups (per-project cost, per-team breakdown).
- [x] 3.4 People/adoption view (per-user rollup within each team).
- [x] 3.5 Governance and collector health (no-capture, unattributed rate, unknown model flags).
- [x] 3.6 Finance cost allocation (`halyard export --format csv` with cost centers).

## 4. Scale and operations

- [x] 4.1 Validate 500-user reporting shape (pure-function aggregation; no DB required).
- [x] 4.2 Define sync failure and retry states.
- [x] 4.3 Define export API/CSV requirements.
- [x] 4.4 Define retention and audit requirements.
