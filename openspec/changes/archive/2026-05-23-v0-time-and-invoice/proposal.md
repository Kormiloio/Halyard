# v0: Time tracking and invoice drafting

## Why

Freelancers waste hours every month on the same loop: scattered time notes,
chasing invoice templates, fighting accounting software they hate. Existing
tools (FreshBooks, QuickBooks, Harvest) are SaaS, lock data in proprietary
databases, and have nothing meaningful in the way of an AI agent.

We're building the smallest version of Halyard that can demo the full thesis
in 60 seconds: log time in natural language, generate an invoice from those
hours, and prove the data is just plain text the user owns.

The deliverable for v0 is *the demo video*, not the binary. The binary exists
to make the video true.

## What's changing

- New CLI binary `halyard` with `init`, `log`, `start`, `stop`, `invoice`,
  and an interactive REPL that drops you into a Claude-powered session.
- New project layout: `halyard.toml`, `clients.toml`, `projects.toml`,
  `time.timeclock`, `invoices/`.
- Default markdown invoice template + typst PDF renderer.
- Single-turn agent loop with three tools: `read_text`, `append_timeclock`,
  `render_invoice`. Plus `run_hledger` for read-only queries. All writes
  require user approval.

## Out of scope (v0)

- Expenses, bank sync, reconciliation → v1
- Local web UI → v1
- Plugin/skill system → v1
- Beancount ledger → v1
- Tax forms, e-file → v3+
- Multi-currency edge cases → v2
