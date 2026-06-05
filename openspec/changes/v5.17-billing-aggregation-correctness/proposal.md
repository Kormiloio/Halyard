# v5.17 — Billing & aggregation correctness

## Why

The pre-release audit (`docs/reviews/2026-06-pre-release-audit.md`) found
several high-severity correctness defects in the money/aggregation paths that
silently produce wrong numbers — the worst kind of bug for a tool whose whole
value proposition is trustworthy AI-spend accounting. These are release
blockers:

- **B14** — `db.py:_sync_sessions` did `",".join(session.mcp_server_names)`,
  but `mcp_server_names` is already a CSV *string*, so `join` iterated it
  character-by-character: `"filesystem,github"` cached as
  `"f,i,l,e,s,y,s,t,e,m,,,g,i,t,h,u,b"`. Every session using an allowlisted
  MCP server corrupted on every `db sync`.
- **B15** — `invoicing.py` used `rate_override or project.hourly_rate or
  _effective_rate(...)`, treating a legitimate `0.0` rate as missing, so a
  comp/free invoice billed the client at a fallback rate.
- **B16** — invoice sessions are selected by `end` (half-open window) but the
  appendix derived the ledger month from `min(s.start)`, mis-allocating a
  session that straddled a month boundary to the wrong period/plan.
- **B17** — the dashboard headline cost used raw `sum(s.cost_usd)` over all
  sessions while every breakdown used `sum_spend(api_only=True)`, so the
  headline never equalled the bars; and `_model_buckets` used different
  billing filters for single- vs multi-model sessions, so identical
  subscription sessions showed cost in one path and `$0` in the other.

## What changed

- **B14:** write `session.mcp_server_names` (the CSV string) directly to the
  cache column (`or ""` for `None`); remove the `",".join`.
- **B15:** explicit `is not None` checks instead of the `or` chain, so a
  `0.0` rate is honored.
- **B16:** derive the appendix month from the invoice period (the same
  `period_start`/`period_end` used for selection), not `min(s.start)`.
- **B17:** compute the headline via the same `sum_spend(api_only=True)`
  (Decimal-quantized) the breakdowns use, and make `_model_buckets`'
  single- and multi-model branches apply the same billing filter.

## Out of scope

- `evidence.py:78`, a second caller of `render_ai_evidence_appendix`, still
  uses the backward-compatible `min(s.start)` default (it passes only a
  period label, often "All time"). Pinning its ledger period is a separate
  follow-up if the evidence artifact needs period-exact ledgers.
- Localhost auth/secret hardening (v5.19) and untrusted-input hardening
  (v5.16) and robustness/data-loss (v5.18) are their own changesets.

## Success criteria

- Multi-server MCP names round-trip through `db sync` uncorrupted.
- A `0.0` rate invoice bills `$0`.
- A month-straddling session is allocated to the period it completed in.
- Dashboard headline cost equals the sum of the breakdown bars; subscription
  sessions are treated identically in single- and multi-model attribution.
- Full suite green; ruff + mypy clean. Each fix has a regression test.
