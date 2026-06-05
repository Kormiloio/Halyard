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

## Gate ✅

Run as part of the whole v5.16–v5.18 batch — see
`openspec/changes/v5.16-untrusted-input-hardening/tasks.md` Gate section.
- [x] Roadmap entry in `openspec/project.md` (entry 90).
