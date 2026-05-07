# Tasks

Implementation checklist for v3 — Org Admin Dashboard.

## 1. Product foundation

- [x] 1.1 Write org admin dashboard PRD.
- [x] 1.2 Define manager, director, CIO, and finance users.
- [ ] 1.3 Define org identity and team mapping model.
- [ ] 1.4 Define cost center mapping model.

## 2. Org data contract

- [ ] 2.1 Define normalized org event schema.
- [ ] 2.2 Preserve local `ai-sessions.log` semantics in sync.
- [ ] 2.3 Define trust labels for aggregates.
- [ ] 2.4 Define privacy boundary and excluded content.

## 3. Dashboard views

- [ ] 3.1 Executive overview.
- [ ] 3.2 Team rollups.
- [ ] 3.3 Project rollups.
- [ ] 3.4 People/adoption view.
- [ ] 3.5 Governance and collector health.
- [ ] 3.6 Finance cost allocation.

## 4. Scale and operations

- [ ] 4.1 Validate 500-user reporting shape.
- [ ] 4.2 Define sync failure and retry states.
- [ ] 4.3 Define export API/CSV requirements.
- [ ] 4.4 Define retention and audit requirements.
