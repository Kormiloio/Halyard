# Halyard

> *A halyard is the line that raises the sails. Pull on it, the sails go up. Pull on this one, your AI work comes into focus.*

**Your AI work leaves a trail. Halyard makes that trail legible, auditable, and client-safe.**

Every AI session — time, tokens, model, cost, project — captured where the work happens,
stored as plain text on your machine, owned by you. No account. No cloud service. No
prompt or code capture. Ever. MIT licensed.

**Status:** alpha, open source — capture loop, reports, invoices, The Bridge, and TUI
in daily use.

---

## What it looks like

**CLI report**
![halyard report output](docs/assets/screenshot-report.png)

**The Bridge — local dashboard**
![The Bridge dashboard](docs/assets/screenshot-dashboard.png)

---

## The problem

You're doing AI-assisted work. At the end of a sprint, a month, or a client engagement,
you can't answer three basic questions:

- What did AI actually cost on this project?
- What did AI help produce — and can you prove it?
- Is your AI spend going in the right direction?

Your tools don't record this. Halyard does.

It runs as lightweight hooks inside Claude Code, Cursor, and Gemini CLI, with
manual/editor-task capture for tools like VS Code where no public AI-session hook
exists. Every session writes one line to a plain-text log you own. From that log:
cost breakdowns, project attribution, invoice evidence, and eventually a signed,
verifiable AI work appendix you can hand to a client.

The privacy promise is unconditional: Halyard captures session metadata, never prompt
content, code context, file contents, or transcripts.

---

## Who it is for

**Individual developers and freelancers** — your primary audience right now.
Your time, your AI spend, and your invoice evidence live as plain text on your
laptop. Halyard helps you prove what happened without exposing prompts or code.
Git it, back it up, sync it however you want. No account. No SaaS. No
proprietary format.

**Small AI shops** — share the same local ledger format across a team.
Project spend, trust-labeled cost allocation, and client-safe appendices built
from individual plain-text logs.

**Enterprise** — the same format will support governance, cost centers, and
cross-tool AI Work Intelligence later. That layer is additive, gated on
design-partner pull, and will not change what local files mean.

---

## How it works

Halyard has three layers:

**Collection** — Lightweight hooks that run where AI work happens. Claude Code,
Cursor, Windsurf, Gemini CLI, and Antigravity hooks capture sessions
automatically; a VS Code
extension captures editing time, branch, and code delta — token counts
unavailable until VS Code/Copilot exposes a public session hook. Since v3.5,
Claude Code sessions are tagged with an advisory **client surface**
(`cli` / `desktop` / `ide`) detected from the local environment. Captured fields
include time, tokens when available, model, cost, project, and branch. Written
to a plain-text log you own. New sessions are appended, and the current
hardening track is making corrections explicit and auditable. Nothing is lost
silently.

**Intelligence** — Analytics built on that log. Local CLI reports, cost-by-project breakdowns, per-model spend, budget alerts, and trust-labeled totals (captured vs. calculated vs. allocated). Works offline, no account required.

**AI Work Ledger** — Cost allocation for seat subscriptions and credit plans. If you pay $200/month for Claude Max, Halyard allocates that cost across your projects proportionally — by active minutes, session count, or credit usage — so you know what each client engagement actually costs. Runs on top of `ai-sessions.log` and `ai-plans.toml`; nothing is written back to the raw log.

**Proof Artifacts** — Invoice evidence today, and a signed attestable AI work
appendix next. The goal is a client-safe artifact that proves AI-assisted work
without showing prompts, transcripts, source code, or file contents.

**The Bridge** — A local dashboard for watching capture happen in real time. Run `halyard dashboard` inside any Halyard project.

**Rich Session Telemetry** — Where tools expose it, Halyard captures operational metadata beyond cost: tool call counts, error rates, wall time vs. active agent time, code delta, and per-model breakdowns. Gemini CLI sessions include full multi-model breakdowns from the history file. These signals surface in the TUI and The Bridge as work-health indicators — not productivity scores, but honest signals of session shape.

**Honors** — A service record that rewards clean proof, not raw hours. Ranks advance on attributed sessions (Deckhand → Commodore), stripes track your watch streak, and eight medals recognize behaviors that matter: completing your first watch, keeping a clean manifest, rescuing adrift sessions, and more. Run `halyard honors` to see your record.

**Friends of the Sea** — One sea creature per completed project, auto-assigned by personality. Projects move through nautical voyage stages (Anchors Aweigh → Making Headway → Rounding the Mark → Flying Colors → Shipshape · Moored) as sessions accumulate. Auto-completes on target hit or inactivity. Run `halyard voyage` to see the roster. Your Captain's Quarters on The Bridge shows a Passport — one stamp per AI tool you've used.

---

## For technical readers

Halyard is a Python 3.11+ local-first CLI and dashboard, not a hosted billing
service. The `halyard` command is a Typer app, reports use Rich, the terminal
dashboard uses Textual, and The Bridge is a small `127.0.0.1` HTTP
server. The durable data model is plain text in the project folder; SQLite is
only a rebuildable read-model cache for faster queries.

The capture pipeline is intentionally simple:

```text
AI tool hook/importer/manual command
  -> normalized AiSession object
  -> append-focused ai-sessions.log line
  -> reports, ledger allocation, dashboard, invoice evidence
```

So: is Halyard "just looking at logs"? Not exactly. It uses the best public
signal each tool exposes:

- **Claude Code**: installs `UserPromptSubmit` and `Stop` hooks. The start hook
  records session start time and git SHA. The stop hook reads the structured
  hook payload; for newer Claude Code formats it can also aggregate token/model
  metadata from the local transcript JSONL path passed by the hook.
- **Cursor**: installs `beforeSubmitPrompt` and `stop` hooks. It reads the stop
  payload and prefers `workspace_roots` for attribution because that is the
  actual editor workspace, not necessarily the shell CWD.
- **Gemini CLI**: installs `SessionStart`, `AfterModel`, and `AfterAgent` hooks.
  `AfterModel` accumulates token usage from `usageMetadata`; `AfterAgent`
  finalizes the session. It integrates deeply with OpenTelemetry (OTLP) to measure
  exact API and tool-execution durations (`api_seconds`, `tool_seconds`) and enriches
  from Gemini's local history file for accurate multi-model token breakdowns, tool-call counts,
  and deterministic cost.
- **Antigravity**: installs a `Stop` hook in `~/.gemini/config/hooks.json` and
  reads the per-conversation transcript JSONL. Antigravity reports no tokens,
  model id, or cost anywhere, so these sessions record **time only** — wall
  clock, message counts, tool calls, errors — and are excluded from spend
  totals rather than counted as `$0.00`. Its `conversations/*.db` store is
  undocumented binary protobuf and is deliberately not read. Despite living
  under `~/.gemini/`, it is a separate product from Gemini CLI and neither
  collector reads the other's files.
- **Codex Desktop**: imports local `~/.codex/sessions/.../rollout-*.jsonl`
  files, extracts timing/model/token metadata, and records imported session IDs
  so repeated imports do not duplicate entries.
- **VS Code / GitHub Copilot**: a local VS Code extension (`vscode-extension/`)
  tracks active editing time, captures branch and code-delta via git, and writes
  sessions through `halyard record-session`. Install the extension from a local
  `.vsix` build; no public Copilot session hook exists yet so token counts are
  not available.

Every collector writes the same normalized record shape: timestamps, tool,
model, tokens when available, cache tokens, cost, billing type, project,
branch, capture source, and attribution provenance. Halyard does not store
prompts, source code, file contents, or full transcripts in `ai-sessions.log`.
When a collector temporarily reads a local transcript or history file, it is
only to extract session metadata.

The log is append-focused. Session records are `s ...` lines; corrections are
separate amendment records keyed by a hash of the original line. Writers
hold an exclusive OS-level file lock (`fcntl.flock` on POSIX, `msvcrt.locking`
on Windows) so concurrent hooks do not interleave writes. Malformed records
are quarantined instead of crashing report generation.

Cost handling is explicit about trust. Direct API usage can be captured or
calculated from tokens and the local pricing table. Seat or credit plans are
allocated at report time from `ai-plans.toml` by active minutes, session count,
or credits. Reports label the result as captured, calculated, allocated,
inferred, mixed, or unallocated so client-facing evidence does not pretend an
estimate is a measurement.

---

## Quickstart

> **Platform:** macOS, Linux, and Windows. The `halyard service install`
> command is macOS-only; other platforms can run `halyard dashboard`
> in a long-lived terminal instead.

### The 3-Minute Start

```bash
pipx install halyard
cd ~/businesses/my-freelance
halyard init

# Guided setup installs supported hooks and checks readiness:
halyard setup

# Verify your hooks and first capture:
halyard doctor --first-capture

# Open the dashboard
halyard dashboard
```

### Daily Workflow

```bash
# Start your human timer (AI sessions are auto-captured in the background)
halyard start acme/auth-migration
# ... do work ...
halyard stop

# Terminal UI
halyard tui

# Ask in natural language — two ways, both read-only:
halyard log "what did I spend this month?"   # from the CLI (local by
                                             # default; --agent claude|openai optional)
#   …or via your coding agent through the MCP server (see below)

# Generate an invoice with an AI usage evidence appendix
halyard invoice acme --month 2026-05 --include-ai-evidence
```

<details>
<summary><b>View Full Command Reference</b></summary>

```bash
# Stats-forward analytics — sessions, streaks, peak hour, model mix
halyard usage --range 30d
halyard usage --range 7d --json   # machine-readable

# --json on report/usage/budget/status/evidence/health/doctor for CI + scripts
halyard report --all --json | jq '.totals.cost_usd'
halyard budget --json | jq '.[] | select(.month.state=="over")'   # spend gate

# Install the background launchd service (macOS):
halyard service install

# Ask your agent about your own AI work (read-only MCP server):
pipx inject halyard mcp   # add the MCP extra to the pipx install
halyard mcp            # stdio MCP server for Claude Code / Cursor

# Install hooks manually:
halyard install-hook          # Claude Code
halyard install-cursor-hook   # Cursor
halyard install-gemini-hook   # Gemini CLI
halyard install-hook-antigravity  # Antigravity (time only, no spend)
halyard install-vscode-tasks  # VS Code manual capture task

# Record VS Code/Copilot work manually
halyard record-session --tool vscode --model github-copilot --minutes 15 --note "Copilot chat"

# Retroactive Gemini import
halyard import-gemini

# Budget limits
halyard set-budget acme --daily 10.00 --monthly 200.00

# AI Work Ledger — allocate seat/credit plan costs by project
halyard report --ledger

# Confirm inferred project attribution from timeclock overlap
halyard confirm-attribution

# Keep pricing table fresh
halyard update-pricing

# Service record & Project voyage roster
halyard honors
halyard voyage
```
</details>

See [`docs/demo.md`](docs/demo.md) for a full walkthrough — self-guided and
live presentation script in one document. If capture does not show up, start
with [`docs/troubleshooting.md`](docs/troubleshooting.md).

## MCP server (ask your agent about your AI work)

`halyard mcp` runs a **read-only** MCP server over stdio so Claude Code,
Cursor, or any MCP client can query your local ledger in-context — e.g.
"how much did I spend this week?", "did this work ship?", "what's my
adrift rate?". It exposes `work_summary`, `sessions`, `spend_in_range`,
`project_breakdown`, `cost_by_model`, and `outcomes_status`. No tool
writes anything; only metadata already in the ledger is returned (never
prompts, code, or transcripts). It needs the optional extra
(`pipx inject halyard mcp`, or `pipx install 'halyard[mcp]'` from a
fresh install).

`halyard init` (and `halyard setup`) **auto-registers** it with every
MCP client detected on your PATH — Claude Code, Cursor, Gemini CLI — so
you never edit a config file. Re-run any time, or register one client
explicitly:

```bash
halyard install-mcp-claude     # or -cursor / -gemini
```

It writes a single `mcpServers.halyard` entry to each client's config
(`~/.claude.json`, `~/.cursor/mcp.json`, `~/.gemini/settings.json`),
preserving every other server. The Halyard repo also ships a ready
[`.mcp.json`](.mcp.json) for Claude Code zero-config pickup in-repo:

```json
{ "mcpServers": { "halyard": { "command": "halyard", "args": ["mcp"] } } }
```

---

## Collector coverage

| Tool | How it's captured | Status |
|------|-------------------|--------|
| Claude Code | `Stop` hook — fires on every session end | Shipped |
| Cursor | `stop` hook — fires when agent completes | Shipped |
| Gemini CLI | `SessionStart` / `AfterModel` / `AfterAgent` hooks + history file enrichment | Shipped |
| Codex Desktop | JSONL session importer | Shipped |
| VS Code / GitHub Copilot | VS Code task + `record-session --tool vscode`; no public Copilot hook yet | Manual capture |
| Windsurf | TBD | Future |
| OpenAI API direct | SDK wrapper or proxy | Future |

Gemini CLI sessions include per-model token breakdowns (flash vs. pro vs. thinking), tool call counts, and accurate multi-model cost — derived from the same history file Gemini CLI uses for its own shutdown summary.

---

## Polyglot ingestion

Tools that are not written in Python can emit sessions directly to the local
Hub:

```bash
halyard spec
samples/emit-session.sh
```

The Hub accepts `POST http://127.0.0.1:4318/v1/ingest` with either a raw
canonical `ai-sessions.log` line or a structured `fields` object. Structured
payloads must include `start`, `end`, `tool`, `model`, `input_tokens`,
`output_tokens`, and `cost_usd`; optional metadata keys are the same keys shown
by `halyard spec`.

```bash
curl -X POST http://127.0.0.1:4318/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"fields":{"start":"2026-05-23T10:00:00","end":"2026-05-23T10:05:00","tool":"custom-tool","model":"model-x","input_tokens":100,"output_tokens":50,"cost_usd":0.01}}'
```

---

## What gets captured

Per session (one line in `ai-sessions.log`):

- Start and end time
- Tool (`claude-code`, `cursor`, `gemini-cli`, `vscode`, …)
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
├── ai-plans.toml         # seat/credit plan definitions for cost allocation
└── invoices/             # generated invoice markdown + PDF
```

Agent state (hooks, API keys, budgets, active timer) lives in `~/.halyard/`, separate from the project folder.

---

## Troubleshooting

### `halyard usage` or the dashboard shows "missing tokens"

Some captured sessions don't carry token data. The dashboard flags them as
`missing tokens` and `halyard usage` reports them under
`token_data_missing_sessions`. Common reasons:

- **Claude Code seat sessions** — when a session is on a credits/seat plan
  rather than the API, token counts may not be available in the hook
  payload. The session is still recorded with `tokens_available=false`;
  cost is reported as `$0.00` because there is no per-session API charge.
  Use [the AI Work Ledger](#what-gets-captured) (`halyard report --ledger`)
  to see allocated subscription cost for these.
- **Manual or VS Code editor-task captures** — sessions recorded via
  `halyard record-session` without an explicit `--input-tokens` /
  `--output-tokens` arrive without token data. This is expected; the
  capture is preserved for time/attribution.
- **Codex imports** — the Codex Desktop import path reads from the local
  rollout JSONL but may not surface token counts in all session formats.
  Import is still useful for attribution and time.

These rows are **not** quarantined and **not** lost — they appear in the
log with `tokens_available=false` so downstream tooling can distinguish
"no data" from "zero usage".

### "Cost shows $0.00 but I know I'm paying for AI"

Halyard records two cost classes:

- **Direct API cost** (`cost_usd` on the session line) — per-call charge
  from the provider, captured when the hook payload includes pricing.
- **Allocated subscription cost** — your $20/month Claude Pro or $200/month
  Claude Max is allocated across captured sessions proportionally. Run
  `halyard report --ledger` to see this. Cost trust labels in the
  dashboard (`captured` / `calculated` / `allocated`) tell you which lens
  you're looking through.

If `cost_usd` is consistently $0.00 *and* you have no `ai-plans.toml`,
create one in the project folder (define your seat/credit plans) so
`halyard report --ledger` can allocate subscription cost.

### Dashboard shows "344 missing tokens" warning

That's the same `token_data_missing_sessions` count surfaced as a pill on
the Usage Analytics panel. It's a counter, not an error — see "missing
tokens" above. If the number is climbing, check that your active AI tool's
hook is sending token data (`halyard doctor` confirms hook health) and
that recent sessions on the API plan aren't being dropped.

---

## How it's being built

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Every feature lives as a change folder under `openspec/changes/` with a proposal, specs, design, and task checklist.

> **Versioning note:** the published PyPI package is `0.x` (currently
> `0.2.1`). The `vN.x` identifiers below (e.g. `v2.24`) are internal
> OpenSpec changeset IDs, **not** release versions — they track
> design history, not what you `pipx install`.

### Current Focus

| Change | Description |
|--------|-------------|
| - | No active focus; all current changes shipped. |

### Shipped

| Change | Description |
|--------|-------------|
| [`v3.6-windsurf-collector`](./openspec/changes/v3.6-windsurf-collector/) | Native collector for Windsurf IDE (Codeium) |
| [`v3.5-claude-code-surface`](./openspec/changes/v3.5-claude-code-surface/) | Advisory client-surface tag (CLI vs. desktop) for Claude Code sessions |
| [`v0-time-and-invoice`](./openspec/changes/v0-time-and-invoice/) | Project skeleton, `halyard init`, human time tracking, invoice generation |
| [`v0.1-log-and-invoice`](./openspec/changes/archive/2026-05-08-v0.1-log-and-invoice/) | `halyard log` natural-language query + `halyard invoice` |
| [`v0.2-ai-agent-loop`](./openspec/changes/archive/2026-05-08-v0.2-ai-agent-loop/) | Structured-output AI agent loop for `halyard log` |
| [`v0.3-provider-neutral-log`](./openspec/changes/archive/2026-05-07-v0.3-provider-neutral-log/) | OpenAI + local model support for `halyard log --agent openai` |
| [`v1-ai-intelligence`](./openspec/changes/archive/2026-05-07-v1-ai-intelligence/) | AI session schema + Claude Code collector + local reports |
| [`v1.5-multi-tool-collectors`](./openspec/changes/archive/2026-05-07-v1.5-multi-tool-collectors/) | Cursor, Gemini CLI, and Codex collectors |
| [`v2-ai-work-ledger`](./openspec/changes/archive/2026-05-07-v2-ai-work-ledger/) | Cost allocation for seat/credit plans, trust-labeled reports, `confirm-attribution`, invoice evidence appendix |
| [`v2-local-activity-dashboard`](./openspec/changes/v2-local-activity-dashboard/) | The Bridge local browser dashboard (`halyard dashboard`) |
| [`v2.1-dynamic-pricing`](./openspec/changes/archive/2026-05-07-v2.1-dynamic-pricing/) | `halyard update-pricing` — live pricing table sync |
| [`v2.2-budget-limits`](./openspec/changes/archive/2026-05-07-v2.2-budget-limits/) | Per-project daily/monthly budget alerts |
| [`v2.3-gemini-history`](./openspec/changes/archive/2026-05-07-v2.3-gemini-history/) | Gemini history file enrichment + `halyard import-gemini` |
| [`v2.4-data-integrity`](./openspec/changes/archive/2026-05-08-v2.4-data-integrity/) | Quarantine, recoverable unattributed log, parser hardening |
| [`v2.5-cli-decoupling`](./openspec/changes/archive/2026-05-07-v2.5-cli-decoupling/) | Service layer extracted from CLI; orchestration module |
| [`v2.6-rich-session-telemetry`](./openspec/changes/archive/2026-05-08-v2.6-rich-session-telemetry/) | Tool calls, errors, wall/active time, code delta, and model breakdown fields |
| [`v2.7-ai-work-health`](./openspec/changes/archive/2026-05-08-v2.7-ai-work-health/) | Local work-health signals such as error rate and repeated attempts |
| [`v2.8-calendar-blocks`](./openspec/changes/archive/2026-05-08-v2.8-calendar-blocks/) | Calendar export for captured sessions; future scheduling is deferred |
| [`v2.9-onboarding-doctor`](./openspec/changes/archive/2026-05-08-v2.9-onboarding-doctor/) | `halyard doctor` setup diagnosis |
| [`v2.10-guided-setup`](./openspec/changes/archive/2026-05-08-v2.10-guided-setup/) | Guided hook setup and first-run readiness flow |
| [`v2.11-hook-normalization`](./openspec/changes/archive/2026-05-08-v2.11-hook-normalization/) | Normalized hook installation commands |
| [`v2.12-glass-cockpit-service`](./openspec/changes/archive/2026-05-14-v2.12-glass-cockpit-service/) | Background service support for the local dashboard |
| [`v2.13-backtracking-attribution`](./openspec/changes/archive/2026-05-08-v2.13-backtracking-attribution/) | Backfill and time-window attribution cleanup |
| [`v2.14-sqlite-read-model`](./openspec/changes/archive/2026-05-14-v2.14-sqlite-read-model/) | SQLite read-model cache over plain-text source files |
| [`v2.15-transaction-history`](./openspec/changes/archive/2026-05-08-v2.15-transaction-history/) | Rate history and invoice audit support |
| [`v4-tui`](./openspec/changes/archive/2026-05-09-v4-tui/) | Textual interactive terminal dashboard (`halyard tui`) |
| [`v2.16-distribution-and-security`](./openspec/changes/v2.16-distribution-and-security/) | Distribution checks, dashboard auth, and launch-readiness hardening |
| [`v2.17-log-integrity`](./openspec/changes/archive/2026-05-14-v2.17-log-integrity/) | Locking, append-only correction records, and shared timer orchestration |
| [`v2.18-cache-and-audit-hardening`](./openspec/changes/archive/2026-05-09-v2.18-cache-and-audit-hardening/) | SQLite cache, invoice audit, pricing, and integrity hardening |
| [`v2.20-security-remediation`](./openspec/changes/archive/2026-05-08-v2.20-security-remediation/) | Targeted security remediation from the first AppSec review |
| [`v2.21-attribution-provenance`](./openspec/changes/archive/2026-05-08-v2.21-attribution-provenance/) | Attribution provenance (`attr_method`) for billing and audit clarity |
| [`v2.22-security-architecture`](./openspec/changes/v2.22-security-architecture/) | Architectural security follow-ups and coverage gaps |
| [`v2.23-usage-analytics`](./openspec/changes/v2.23-usage-analytics/) | Stats-forward usage analytics: activity heatmap, streaks, peak hour, and model share |
| [`v2.24-outcome-metadata`](./openspec/changes/archive/2026-05-09-v2.24-outcome-metadata/) | Branch as first-class field, commit count, code delta, PR linkage (`halyard outcome sync`) |
| [`v2.25-honors-and-achievements`](./openspec/changes/archive/2026-05-09-v2.25-honors-and-achievements/) | Ranks, stripes, medals, and service record (`halyard honors`) |
| [`v2.26-passport-and-friends`](./openspec/changes/archive/2026-05-09-v2.26-passport-and-friends/) | Passport stamps + Friends of the Sea voyage stages and sea creatures (`halyard voyage`) |

### Gated Future Work

| Change | Description |
|--------|-------------|
| [`v3.0-outcome-graph`](./openspec/changes/v3.0-outcome-graph/) | Connect AI sessions to commits, PRs, tests, and outcomes; gated on design-partner pull |
| [`v3-org-admin-dashboard`](./openspec/changes/archive/2026-05-08-v3-org-admin-dashboard/) | Team, manager, CIO, and finance rollups; deferred until enterprise readiness |

---

## Roadmap

- **Shipped** — OSS launch (v0.2.1), honors and achievements (`halyard honors`),
  Passport stamps, Friends of the Sea voyage stages (`halyard voyage`), outcome
  metadata v2.24: branch field, commit count, code delta, `halyard outcome sync`,
  and Claude Code client-surface detection (v3.5).
- **Then** — Attestable AI work appendix (v2.19): signed, client-safe proof of
  AI-assisted work, enriched with commit and PR signals.
- **Later, if design partners ask** — Outcome graph (v3.0): connect sessions to
  commits, PRs, tests, and deliverables.
- **Further out** — Redacted sync, org rollups, governance, finance exports, and
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

Early but open. The project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec)
for spec-driven development — every feature has a `proposal.md`, `design.md`,
`specs/`, and `tasks.md` before code is written. See `openspec/changes/` for
what is actively being built.

**To contribute:**
- Browse `openspec/changes/` for open changesets.
- Check the `tasks.md` in any changeset for unchecked items.
- Open an issue before a PR if you are proposing a new feature — start with a
  one-paragraph proposal so we can align on fit before you write code.
- Bug reports and docs improvements need no prior discussion.
- The test suite is `pytest`; coverage requirements are enforced. Run
  `python -m pytest` before submitting.

If something is confusing, a docs issue is as valuable as a code PR.

## License

MIT.

---

A [Kormilo LLC](https://kormilo.io) project.
