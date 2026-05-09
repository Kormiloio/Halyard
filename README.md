# Halyard

> *A halyard is the line that raises the sails. Pull on it, the sails go up. Pull on this one, your AI work comes into focus.*

**The open AI work ledger.** For individuals who need to prove what they did,
and teams who need to know what they are spending. Time, tokens, models, and
cost - captured where the work happens, owned by you, readable by anyone.

**Status:** alpha. The local ledger, multi-tool capture, reports, invoices,
Glass Cockpit, TUI, and REPL are shipped and in daily use. Current work is
focused on security hardening, log integrity, and attestable AI work evidence.

---

## The problem

You're doing AI-assisted work. So is your team. So is every engineering department at every company that's serious about staying competitive.

Nobody knows what it is actually costing. Nobody has clean proof of what AI
helped produce. Time tracking tools do not know about tokens. Finance
dashboards do not know which model you used. Productivity tools do not capture
the mix of human judgment and AI execution that makes modern work happen.

The instruments don't exist yet. Halyard builds them.

Read more about the product direction in
[`Current Direction`](docs/current-direction.md) and
[`AI Work Intelligence`](docs/AI-work-intelligence.md).

---

## Two audiences, one platform

**For the individual developer or freelancer:**
Your time, your AI spend, and your invoice evidence live as plain text on your
laptop. Halyard helps you prove what happened without exposing prompts or code.
Git it, back it up, sync it however you want. No SaaS subscription required. No
proprietary format.

**For small AI shops and teams:**
Shared evidence, project spend, trust-labeled cost allocation, and client-safe
appendices built from the same local ledgers.

**For future enterprise buyers:**
Cross-tool AI Work Intelligence without default prompt or code capture:
governance, cost centers, redacted sync, and effectiveness signals. This layer
is additive and gated on design-partner pull and security readiness.

The solo developer experience is the entry point. The enterprise layer is optional, additive, and built on the same open data format.

---

## How it works

Halyard has three layers:

**Collection** — Lightweight hooks that run where AI work happens. Claude Code,
Cursor, and Gemini CLI hooks capture every session: time, tokens, model, cost,
project, branch. Written to a plain-text log you own. New sessions are
appended, and the current hardening track is making corrections explicit and
auditable. Nothing is lost silently.

**Intelligence** — Analytics built on that log. Local CLI reports, cost-by-project breakdowns, per-model spend, budget alerts, and trust-labeled totals (captured vs. calculated vs. allocated). Works offline, no account required.

**AI Work Ledger** — Cost allocation for seat subscriptions and credit plans. If you pay $200/month for Claude Max, Halyard allocates that cost across your projects proportionally — by active minutes, session count, or credit usage — so you know what each client engagement actually costs. Runs on top of `ai-sessions.log` and `ai-plans.toml`; nothing is written back to the raw log.

**Proof Artifacts** — Invoice evidence today, and a signed attestable AI work
appendix next. The goal is a client-safe artifact that proves AI-assisted work
without showing prompts, transcripts, source code, or file contents.

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
# Guided setup installs supported hooks and checks readiness:
halyard setup

# Or install hooks manually:
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

# Coming next: signed, verifiable AI work appendix
# halyard appendix create --client acme --period 2026-05

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
├── ai-sessions.log       # AI usage events (plain text, append-focused)
├── ledger.beancount      # Beancount double-entry ledger
└── invoices/             # generated invoice markdown + PDF
```

Agent state (hooks, API keys, budgets, active timer) lives in `~/.halyard/`, separate from the project folder.

---

## How it's being built

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Every feature lives as a change folder under `openspec/changes/` with a proposal, specs, design, and task checklist.

### Current Focus

| Change | Description |
|--------|-------------|
| [`v2.16-distribution-and-security`](./openspec/changes/v2.16-distribution-and-security/) | Distribution checks, dashboard auth, and launch-readiness hardening |
| [`v2.17-log-integrity`](./openspec/changes/v2.17-log-integrity/) | Locking, append-only correction records, and shared timer orchestration |
| [`v2.18-cache-and-audit-hardening`](./openspec/changes/v2.18-cache-and-audit-hardening/) | SQLite cache, invoice audit, pricing, and integrity hardening |
| [`v2.19-attestable-appendix`](./openspec/changes/v2.19-attestable-appendix/) | Signed, verifiable, privacy-preserving AI work appendix |
| [`v2.20-security-remediation`](./openspec/changes/v2.20-security-remediation/) | Targeted security remediation from the first AppSec review |
| [`v2.21-attribution-provenance`](./openspec/changes/v2.21-attribution-provenance/) | Attribution provenance (`attr_method`) for billing and audit clarity |
| [`v2.22-security-architecture`](./openspec/changes/v2.22-security-architecture/) | Architectural security follow-ups and coverage gaps |

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
| [`v2.6-rich-session-telemetry`](./openspec/changes/v2.6-rich-session-telemetry/) | Tool calls, errors, wall/active time, code delta, and model breakdown fields |
| [`v2.7-ai-work-health`](./openspec/changes/v2.7-ai-work-health/) | Local work-health signals such as error rate and repeated attempts |
| [`v2.8-calendar-blocks`](./openspec/changes/v2.8-calendar-blocks/) | Calendar export for captured sessions; future scheduling is deferred |
| [`v2.9-onboarding-doctor`](./openspec/changes/v2.9-onboarding-doctor/) | `halyard doctor` setup diagnosis |
| [`v2.10-guided-setup`](./openspec/changes/v2.10-guided-setup/) | Guided hook setup and first-run readiness flow |
| [`v2.11-hook-normalization`](./openspec/changes/v2.11-hook-normalization/) | Normalized hook installation commands |
| [`v2.12-glass-cockpit-service`](./openspec/changes/v2.12-glass-cockpit-service/) | Background service support for the local dashboard |
| [`v2.13-backtracking-attribution`](./openspec/changes/v2.13-backtracking-attribution/) | Backfill and time-window attribution cleanup |
| [`v2.14-sqlite-read-model`](./openspec/changes/v2.14-sqlite-read-model/) | SQLite read-model cache over plain-text source files |
| [`v2.15-transaction-history`](./openspec/changes/v2.15-transaction-history/) | Rate history and invoice audit support |
| [`v4-tui`](./openspec/changes/v4-tui/) | Textual interactive terminal dashboard (`halyard tui`) |

### Gated Future Work

| Change | Description |
|--------|-------------|
| [`v3.0-outcome-graph`](./openspec/changes/v3.0-outcome-graph/) | Connect AI sessions to commits, PRs, tests, and outcomes; gated on design-partner pull |
| [`v3-org-admin-dashboard`](./openspec/changes/v3-org-admin-dashboard/) | Team, manager, CIO, and finance rollups; deferred until enterprise readiness |

---

## Roadmap

- **Now** — Security hardening, log integrity, pricing/cache/audit reliability.
- **Next** — Attestable AI work appendix: signed client-safe proof of AI-assisted work.
- **Then, if design partners ask** — Outcome graph: connect sessions to commits,
  PRs, tests, and deliverables.
- **Later** — Redacted sync, org rollups, governance, finance exports, and
  enterprise reporting.

---

## Non-negotiables

These hold at every tier:

- **Local-first.** The core product runs offline. Cloud is optional and additive.
- **Plain text forever.** Your data is yours, in formats that outlast any startup.
- **Files are the source of truth.** No hidden state, no proprietary database.
- **Append-only direction.** New sessions are appended. Corrections are explicit
  and auditable; attribution cleanup is being hardened toward append-only
  correction records.
- **No silent writes.** Every AI-proposed change is shown before it's applied.
- **MIT licensed.** Permissively. Forever.

---

## Contributing

Early but open. See the openspec change folders for what's actively being built. Issues and PRs welcome — start with a proposal.

## License

MIT.

---

A [Kormilo LLC](https://kormilo.io) project.
