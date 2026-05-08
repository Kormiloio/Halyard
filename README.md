# Halyard

> *A halyard is the line that raises the sails. Pull on it, the sails go up. Pull on this one, your AI work comes into focus.*

**AI Work Intelligence Infrastructure.** Time, tokens, models, and cost — captured where the work happens, owned by you, readable by anyone.

**Status:** alpha. v0–v2, v4 TUI, and interactive REPL shipped and in daily use.

---

## The problem

You're doing AI-assisted work. So is your team. So is every engineering department at every company that's serious about staying competitive.

Nobody knows what it's actually costing. Nobody can measure whether it's working. Time tracking tools don't know about tokens. Finance dashboards don't know which model you used. Productivity tools don't capture the mix of human judgment and AI execution that makes modern work happen.

The instruments don't exist yet. Halyard builds them.

---

## Two audiences, one platform

**For the individual developer or freelancer:**
Your time, your AI spend, and your invoices live as plain text on your laptop. An AI agent (Claude) reads and writes them on your behalf. Git it, back it up, sync it however you want. No SaaS subscription required. No proprietary format. Compatible with the entire plaintext-accounting ecosystem.

**For engineering teams and enterprises:**
A unified view of AI work across your organization — spend by team, by project, by model, over time. Cost attribution. Productivity trends. Compliance audit trails. The data your CTO needs to answer "what are we getting for our AI investment?"

The solo developer experience is the entry point. The enterprise layer is optional, additive, and built on the same open data format.

---

## How it works

Halyard has three layers:

**Collection** — Lightweight hooks that run where AI work happens. Claude Code, Cursor, and Gemini CLI hooks capture every session: time, tokens, model, cost, project, branch. Written to a plain-text append-only log you own. Nothing is lost silently.

**Intelligence** — Analytics built on that log. Local CLI reports, cost-by-project breakdowns, per-model spend, budget alerts, and trust-labeled totals (captured vs. calculated vs. allocated). Works offline, no account required.

**AI Work Ledger** — Cost allocation for seat subscriptions and credit plans. If you pay $200/month for Claude Max, Halyard allocates that cost across your projects proportionally — by active minutes, session count, or credit usage — so you know what each client engagement actually costs. Runs on top of `ai-sessions.log` and `ai-plans.toml`; nothing is written back to the raw log.

**Glass Cockpit** — A local dashboard for watching capture happen in real time. Run `halyard dashboard` inside any Halyard project.

**Rich Session Telemetry** — Where tools expose it, Halyard captures operational metadata beyond cost: tool call counts, error rates, wall time vs. active agent time, code delta, and per-model breakdowns. Gemini CLI sessions include full multi-model breakdowns from the history file. These signals surface in the TUI and Glass Cockpit as work-health indicators — not productivity scores, but honest signals of session shape.

---

## Quickstart

```bash
pipx install halyard
cd ~/businesses/my-freelance
halyard init

# Human time
halyard start acme/auth-migration
# ... do work ...
halyard stop

# Check what's been captured
halyard log "what did I spend this month?"
halyard log "what did Cursor cost this week?"
halyard report
halyard dashboard

# Interactive REPL — natural-language queries over your work data
halyard

# Terminal dashboard
halyard tui

# AI sessions are captured automatically by hooks
# Install hooks once per tool:
halyard install-hook          # Claude Code
halyard install-cursor-hook   # Cursor
halyard install-gemini-hook   # Gemini CLI

# Diagnose setup and verify first capture
halyard doctor
halyard doctor --first-capture

# Retroactive Gemini import
halyard import-gemini

# Budget limits
halyard set-budget acme --daily 10.00 --monthly 200.00
halyard budget

# AI Work Ledger — allocate seat/credit plan costs by project
halyard report --ledger

# Confirm inferred project attribution from timeclock overlap
halyard confirm-attribution

# Invoice with AI usage evidence appendix
halyard invoice acme --period 2026-05 --include-ai-evidence

# Keep pricing table fresh
halyard update-pricing
```

See [`docs/demo.md`](docs/demo.md) for a full 60-second walkthrough. If capture
does not show up, start with [`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Collector coverage

| Tool | How it's captured | Status |
|------|-------------------|--------|
| Claude Code | `Stop` hook — fires on every session end | Shipped |
| Cursor | `stop` hook — fires when agent completes | Shipped |
| Gemini CLI | `SessionStart` / `AfterModel` / `AfterAgent` hooks + history file enrichment | Shipped |
| Codex Desktop | JSONL session importer | Shipped |
| GitHub Copilot | No public hook API | Future |
| Windsurf | TBD | Future |
| OpenAI API direct | SDK wrapper or proxy | Future |

Gemini CLI sessions include per-model token breakdowns (flash vs. pro vs. thinking), tool call counts, and accurate multi-model cost — derived from the same history file Gemini CLI uses for its own shutdown summary.

---

## What gets captured

Per session (one line in `ai-sessions.log`):

- Start and end time
- Tool (`claude-code`, `cursor`, `gemini-cli`, …)
- Model identifier
- Input tokens, output tokens, cache read/write
- Cost in USD (from local pricing table, snapshotted at capture)
- Project attribution (`client:project`)
- Git branch
- Billing model (`api`, `credits`, `seat`)
- Capture source (`hook`, `sdk`, `manual`)

What is **not** captured: prompt content, code context, file contents, any user data beyond session metadata.

---

## Budget limits

Set per-project spend limits in your personal `~/.halyard/budgets.toml` — never committed to the repo. Warnings fire at session start when you've exceeded a daily or monthly threshold. Sessions always proceed; this is instrumentation, not a gate.

```bash
halyard set-budget acme --daily 15.00 --monthly 300.00
halyard budget   # shows current spend vs limits across all projects
```

---

## Data files

```
my-business/
├── halyard.toml          # business name, currency, invoice counter
├── clients.toml          # array of clients
├── projects.toml         # array of projects
├── time.timeclock        # hledger-compatible human time log
├── ai-sessions.log       # AI usage events (append-only, open format)
├── ledger.beancount      # Beancount double-entry ledger
└── invoices/             # generated invoice markdown + PDF
```

Agent state (hooks, API keys, budgets, active timer) lives in `~/.halyard/`, separate from the project folder.

---

## How it's being built

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Every feature lives as a change folder under `openspec/changes/` with a proposal, specs, design, and task checklist.

### Shipped

| Change | Description |
|--------|-------------|
| [`v0-time-and-invoice`](./openspec/changes/v0-time-and-invoice/) | Project skeleton, `halyard init`, human time tracking, invoice generation |
| [`v0.1-log-and-invoice`](./openspec/changes/v0.1-log-and-invoice/) | `halyard log` natural-language query + `halyard invoice` |
| [`v0.2-ai-agent-loop`](./openspec/changes/v0.2-ai-agent-loop/) | Structured-output AI agent loop for `halyard log` |
| [`v0.3-provider-neutral-log`](./openspec/changes/v0.3-provider-neutral-log/) | OpenAI + local model support for `halyard log --agent openai` |
| [`v1-ai-intelligence`](./openspec/changes/archive/2026-05-07-v1-ai-intelligence/) | AI session schema + Claude Code collector + local reports |
| [`v1.5-multi-tool-collectors`](./openspec/changes/archive/2026-05-07-v1.5-multi-tool-collectors/) | Cursor, Gemini CLI, and Codex collectors |
| [`v2-ai-work-ledger`](./openspec/changes/v2-ai-work-ledger/) | Cost allocation for seat/credit plans, trust-labeled reports, `confirm-attribution`, invoice evidence appendix |
| [`v2-local-activity-dashboard`](./openspec/changes/v2-local-activity-dashboard/) | Glass Cockpit local browser dashboard (`halyard dashboard`) |
| [`v2.1-dynamic-pricing`](./openspec/changes/archive/2026-05-07-v2.1-dynamic-pricing/) | `halyard update-pricing` — live pricing table sync |
| [`v2.2-budget-limits`](./openspec/changes/archive/2026-05-07-v2.2-budget-limits/) | Per-project daily/monthly budget alerts |
| [`v2.3-gemini-history`](./openspec/changes/archive/2026-05-07-v2.3-gemini-history/) | Gemini history file enrichment + `halyard import-gemini` |
| [`v2.4-data-integrity`](./openspec/changes/v2.4-data-integrity/) | Quarantine, recoverable unattributed log, parser hardening |
| [`v2.5-cli-decoupling`](./openspec/changes/v2.5-cli-decoupling/) | Service layer extracted from CLI; orchestration module |
| [`v4-tui`](./openspec/changes/v4-tui/) | Textual interactive terminal dashboard (`halyard tui`) |

### Proposed

| Change | Description |
|--------|-------------|
| [`v3-org-admin-dashboard`](./openspec/changes/v3-org-admin-dashboard/) | Team, manager, CIO, and finance rollups |

---

## Roadmap

- **v3** — Org admin dashboard: manager/CIO rollups, governance, finance exports.
- **v5+** — Productivity measurement, ROI reporting, outcome-based billing support.

---

## Non-negotiables

These hold at every tier:

- **Local-first.** The core product runs offline. Cloud is optional and additive.
- **Plain text forever.** Your data is yours, in formats that outlast any startup.
- **Files are the source of truth.** No hidden state, no proprietary database.
- **Append-only logs.** Raw logs are never rewritten. Corrections happen in the analytics layer.
- **No silent writes.** Every AI-proposed change is shown before it's applied.
- **MIT licensed.** Permissively. Forever.

---

## Contributing

Early but open. See the openspec change folders for what's actively being built. Issues and PRs welcome — start with a proposal.

## License

MIT.

---

A [Kormilo LLC](https://kormilo.io) project.
