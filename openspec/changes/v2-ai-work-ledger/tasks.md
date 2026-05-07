# Tasks

Implementation checklist for v2 — AI Work Ledger.

## 1. Product and schema foundation

- [x] 1.1 Write product PRD for the AI Work Ledger.
- [ ] 1.2 Define `ai-plans.toml` schema with plan, seat, credit, and allocation
      fields.
- [ ] 1.3 Add Pydantic models for AI plans and allocation rules.
- [ ] 1.4 Add TOML reader for `ai-plans.toml`.
- [ ] 1.5 Update `halyard init` to create a commented `ai-plans.toml` template.

## 2. Cost allocation

- [ ] 2.1 Implement direct API cost aggregation from `ai-sessions.log`.
- [ ] 2.2 Implement credit cost conversion when configured exchange rates exist.
- [ ] 2.3 Implement seat allocation by active minutes.
- [ ] 2.4 Implement seat allocation by session count.
- [ ] 2.5 Mark allocated and inferred costs distinctly in report data.

## 3. Attribution

- [ ] 3.1 Join AI sessions to project records through `project=client:project`.
- [ ] 3.2 Detect unattributed sessions and surface them in reports.
- [ ] 3.3 Infer attribution from overlapping `time.timeclock` windows.
- [ ] 3.4 Add a confirmation flow for inferred attribution before writing any
      corrections.

## 4. Combined reporting

- [ ] 4.1 Extend `halyard report` with project/client/date filters.
- [ ] 4.2 Show human hours and AI usage in one project summary.
- [ ] 4.3 Show direct API cost, allocated plan cost, and total AI cost.
- [ ] 4.4 Show breakdowns by tool and model.
- [ ] 4.5 Add tests for empty plans, direct API costs, seat allocation, credits,
      and unattributed sessions.

## 5. Invoice evidence

- [ ] 5.1 Add `--include-ai-evidence` option to invoice generation.
- [ ] 5.2 Render markdown invoice appendix from combined report data.
- [ ] 5.3 Label estimated, allocated, and inferred values clearly.
- [ ] 5.4 Ensure prompt/code content is never included by default.
- [ ] 5.5 Add golden-file tests for the invoice appendix.

## 6. Documentation and demo

- [ ] 6.1 Update README with the AI Work Ledger positioning.
- [ ] 6.2 Add a sample `ai-sessions.log` and `ai-plans.toml`.
- [ ] 6.3 Add a 60-second demo script showing human time plus AI cost by
      project.
- [ ] 6.4 Document the trust model: captured vs calculated vs allocated vs
      inferred.
