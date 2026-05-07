# Tasks

Implementation checklist for v2 — AI Work Ledger.

## 1. Product and schema foundation

- [x] 1.1 Write product PRD for the AI Work Ledger.
- [x] 1.2 Define `ai-plans.toml` schema with plan, seat, credit, and allocation
      fields.
- [x] 1.3 Add Pydantic models for AI plans and allocation rules.
- [x] 1.4 Add TOML reader for `ai-plans.toml`.
- [x] 1.5 Update \`halyard init\` to create a commented \`ai-plans.toml\` template.

## 2. Cost allocation

- [x] 2.1 Implement direct API cost aggregation from `ai-sessions.log`.
- [x] 2.2 Implement credit cost conversion when configured exchange rates exist.
- [x] 2.3 Implement seat allocation by active minutes.
- [x] 2.4 Implement seat allocation by session count.
- [x] 2.5 Mark allocated and inferred costs distinctly in report data.

## 3. Attribution

- [x] 3.1 Join AI sessions to project records through `project=client:project`.
- [x] 3.2 Detect unattributed sessions and surface them in reports.
- [x] 3.3 Infer attribution from overlapping `time.timeclock` windows.
- [x] 3.4 Add a confirmation flow for inferred attribution before writing any
      corrections.

## 4. Combined reporting

- [x] 4.1 Extend `halyard report` with project/client/date filters.
- [x] 4.2 Show human hours and AI usage in one project summary.
- [x] 4.3 Show direct API cost, allocated plan cost, and total AI cost.
- [x] 4.4 Show breakdowns by tool and model.
- [x] 4.5 Add tests for empty plans, direct API costs, seat allocation, credits,
      and unattributed sessions.

## 5. Invoice evidence

- [x] 5.1 Add `--include-ai-evidence` option to invoice generation.
- [x] 5.2 Render markdown invoice appendix from combined report data.
- [x] 5.3 Label estimated, allocated, and inferred values clearly.
- [x] 5.4 Ensure prompt/code content is never included by default.
- [x] 5.5 Add golden-file tests for the invoice appendix.

## 6. Documentation and demo

- [x] 6.1 Update README with the AI Work Ledger positioning.
- [x] 6.2 Add a sample `ai-sessions.log` and `ai-plans.toml`.
- [x] 6.3 Add a 60-second demo script showing human time plus AI cost by
      project.
- [x] 6.4 Document the trust model: captured vs calculated vs allocated vs
      inferred.
