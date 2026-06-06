# v5.17 — Tasks

Source: `docs/reviews/2026-06-pre-release-audit.md`. All implemented in the
parallel blocker-fix workflow (2026-06-05) and verified by the whole-batch
gate (see v5.16 tasks.md Gate section: 1614 passed, ruff+mypy clean).

## B14 — db mcp_server_names CSV corruption [db.py] ✅

- [x] Write `session.mcp_server_names or ""` directly (remove `",".join`).
- [x] Regression test (tests/test_v517_b14_db_mcp_csv.py): multi-server CSV
      round-trips uncorrupted; empty/None still works.

## B15 — zero rate treated as missing [invoicing.py] ✅

- [x] Replace `rate_override or project.hourly_rate or _effective_rate(...)`
      with explicit `is not None` checks.
- [x] Regression test (tests/test_v517_b15_b16_invoicing.py): `0.0` rate
      bills `$0`; a real positive rate still applies.

## B16 — month-boundary appendix mis-allocation [invoicing.py] ✅

- [x] Derive appendix month from the invoice period, not `min(s.start)`.
- [x] Regression test: a session started 04-30 23:50 / ended 05-01 00:30 is
      allocated to May.
- Follow-up (out of scope): `evidence.py:78` caller still uses the
  `min(s.start)` default — pin its period only if the evidence artifact needs
  period-exact ledgers.

## B17 — headline cost ≠ sum of bars; phantom subscription cost [usage.py] ✅

- [x] Headline `total_cost_usd` via `sum_spend(selected)` (same convention as
      the bars), not raw `sum(s.cost_usd)`.
- [x] `_model_buckets` single- and multi-model branches use the same billing
      filter.
- [x] Regression test (tests/test_v517_b17_usage_agg.py): mixed-billing set's
      headline equals the bar sum; subscription session treated consistently.
- Behavior change recorded: headline now excludes credit/subscription cost;
      no existing test encoded the old inconsistent numbers (searched).

## Follow-up fixes (owner code review, 2026-06-05) ✅

Two billing bugs the multi-agent audit missed, found by the owner's parallel
review:

- [x] **B24 — cross-client project-slug collision:** `_read_projects` keyed
      projects by bare `slug`, but slugs are only unique *within* a client, so
      two clients sharing a slug (e.g. `web`) collided — an invoice could use
      the wrong client's project name and hourly rate (confirmed: an Acme
      invoice billed Globex's $220 rate). Key by `f"{client_slug}:{slug}"` and
      look up by the full account. Test in `tests/test_review_p1_followups.py`.
- [x] **B25 — round the money, not the hours:** the line-item amount was
      computed from hours pre-rounded to 0.01, over-billing sub-minute work
      (1 min @ $150/h billed $3.00 via 0.02h instead of the exact $2.50).
      Compute the amount from exact minutes and round only the final dollar
      figure (owner decision); `hours` stays 2-decimal for display. Test in
      `tests/test_review_p1_followups.py`.

## Gate ✅

Run as part of the whole v5.16–v5.18 batch — see
`openspec/changes/v5.16-untrusted-input-hardening/tasks.md` Gate section.
- [x] Roadmap entry in `openspec/project.md` (entry 90).
