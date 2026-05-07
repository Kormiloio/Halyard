# PRD: Halyard

**Status:** Living document — update as the product direction evolves.  
**Last meaningful update:** May 2026

---

## What Halyard Is

Halyard is AI work intelligence infrastructure. It captures where AI-assisted work
happens — time, tokens, models, cost, project attribution — and turns that data
into actionable intelligence for individuals and organizations alike.

For the **solo developer or freelancer**: human time, AI spend, and invoice
evidence as plain text on your machine, operated by CLI. No account required.
Works offline. Data is yours, in your folder, forever.

For **engineering teams and enterprises**: unified visibility into AI investment,
productivity, and cost allocation across the organization — built on the same
open data format, extended with a cloud sync and reporting layer.

The individual experience is the entry point. The enterprise layer is optional,
additive, and never changes what the local files mean.

---

## The Problem

Developers and teams are hired to produce outcomes with AI. The real work is a
mix of human judgment and AI tool sessions across Claude Code, Cursor, Codex,
Gemini CLI, and API calls. But:

- **Time trackers** only capture the human clock.
- **Finance tools** only see monthly vendor bills.
- **AI tool dashboards** are siloed — Anthropic shows Claude usage, Google shows
  Gemini usage, nowhere shows the whole picture.
- **No tool** attributes AI spend to client projects, git branches, or
  deliverables.

Nobody can answer, with local evidence:

> For this client project, how much human time and AI resource usage went into
> the work, and what did it cost?

Or, at the team level:

> What is our organization getting for its AI investment?

The instruments don't exist. Halyard builds them.

---

## Strategic Thesis

**The collection protocol is the moat.**

`ai-sessions.log` and the collectors that write to it are open source (MIT).
Enterprise buyers can audit exactly what the agent captures. The analytics and
cloud layers built on top are where the business model lives.

This mirrors the OpenTelemetry model: open instrumentation standard, proprietary
analytics on top. The difference is Halyard owns both sides.

The plaintext files are the durable asset. The CLI, dashboard, and cloud sync
are views over that asset. A future in which ten tools write compatible
`ai-sessions.log` entries — and Halyard is the analytics layer — is a better
outcome than a future in which Halyard is the only tool that can capture.

---

## Two-Audience Invariant

Every product decision must satisfy both:

**1. Solo developer:** Works offline. No account. No setup beyond `halyard init`.
Data is theirs, in their folder, forever. The best capture is invisible: they do
the work and the ledger fills in.

**2. Enterprise buyer:** Data format is auditable, structured, and exportable.
The cloud layer ingests `ai-sessions.log` without transformation. Nothing in the
local product precludes adding SSO, multi-tenancy, or compliance later.

When these two audiences pull in different directions, prefer the solo developer
experience. The enterprise layer adds to the local foundation — it must never
require it to change.

---

## Product Ladder

Halyard ships in layers, each proving the next:

| Layer | Name | Question answered | Status |
|-------|------|-------------------|--------|
| v0 | Time and Invoice | How much human time did this cost? | Shipped |
| v1 | AI Intelligence | What AI did I use and what did it cost? | Shipped |
| v1.5 | Multi-Tool Collectors | Capture AI work across all tools, everywhere | Shipped |
| v2 | AI Work Ledger + Dashboard | What did AI-assisted work cost per project? | Shipped |
| v3 | Org Admin Dashboard | What is our organization getting for its AI investment? | Specced |

Each layer depends on the previous. The local instrument panel must work before
building the org rollup. The open collection protocol must exist before the
analytics layer has anything to analyze.

---

## Core Concepts

### Human time
The clock time a person spends directing, reviewing, building, communicating,
and making decisions on a project. Stored in `time.timeclock` (hledger timeclock
format). Tracked with `halyard in / out`.

### AI session
A bounded unit of AI tool activity: a Claude Code session, a Cursor stop event,
a Gemini CLI turn, a Codex Desktop session, or a direct API call. Stored as one
line in `ai-sessions.log`. Fields: start, end, tool, model, input tokens, output
tokens, cost, and optional key=value pairs for project, branch, cache, billing
model, and more.

### Ambient capture
Sessions are captured automatically wherever the developer is working — not only
inside a Halyard project directory. The **hub** (a single designated project)
acts as the global fallback log. **Git inference** (`git remote get-url origin`)
auto-tags sessions with project slug and branch when no active timer is running.

### Project attribution
Mapping a session to a `client:project` slug. Priority order:
1. Active timer (`halyard in acme:auth`)
2. Explicit git mapping (`~/.halyard/repos.toml`)
3. Auto-derived git slug (`git/<repo-name>`)
4. Unattributed (recoverable later with `halyard assign-unattributed`)

### AI plan / seat cost
Many AI tools charge flat monthly fees (Cursor, GitHub Copilot, Claude Max) or
opaque credits, not per-token. `ai-plans.toml` configures these plans. The
ledger allocates plan cost to projects by session count, active minutes, or
manual weight — not at capture time, but at report time.

### Trust label
Every cost figure carries a trust level: **captured** (real token data),
**calculated** (derived from pricing table), **allocated** (proportioned from
a plan), or **inferred** (estimated). Reports and dashboards show trust labels
so users understand what they're looking at.

---

## What Is Captured

Per session:
- Start and end time (local, to the second)
- Tool slug (`claude-code`, `cursor`, `gemini-cli`, `codex`, etc.)
- Model identifier
- Input tokens, output tokens (and cache read/write where available)
- Cost in USD (snapshotted at capture time from the pricing table)
- Project attribution
- Git branch (`tags=branch:<name>`)
- Billing model (`api`, `credits`, `seat`)
- Capture source (`hook`, `sdk`, `manual`)

What is **not** captured by default:
- Prompt or conversation content
- Code context or file contents
- Any user data beyond session metadata

Sensitive content capture is never a default and would require a separate,
explicit opt-in feature with its own spec.

---

## Collector Coverage

| Tool | Mechanism | Status |
|------|-----------|--------|
| Claude Code | `Stop` hook | Shipped |
| Cursor | `stop` hook | Shipped |
| Gemini CLI | `SessionStart` / `AfterModel` / `AfterAgent` hooks | Shipped |
| Codex Desktop | JSONL session file importer | Shipped |
| GitHub Copilot | TBD (no public hook API) | Future |
| Windsurf | TBD | Future |
| OpenAI API | Proxy or SDK wrapper | Future |
| Anthropic API (direct) | Already via Claude Code hook | Partial |

The API proxy approach (intercepting HTTPS traffic) was evaluated and rejected
for v1.5 in favor of per-tool hooks. See
`openspec/changes/v1.5-multi-tool-collectors/proposal.md` for the full
rationale.

---

## Non-Negotiables

These apply to every layer of the product:

1. **Local-first.** No required cloud service. The core product runs offline.
2. **Plain text forever.** `time.timeclock`, `ai-sessions.log`, TOML configs.
   No SQLite as source of truth. No proprietary formats.
3. **Files are the source of truth.** Any UI is a view onto the files.
4. **Append-only logs.** Raw logs are never rewritten. Corrections happen in
   the analytics layer only.
5. **MIT licensed.** The collection protocol and CLI are open source, permanently.
6. **No silent writes.** Modifications to user data are proposed, not applied
   automatically.

---

## UX Principles

- **The best capture is invisible.** Users do the work; the ledger fills in.
- **Uncertainty is explicit.** Reports distinguish measured, calculated,
  allocated, and inferred values. Never present an estimate as a fact.
- **CLI is the fastest workflow.** The dashboard makes the system legible, but
  never becomes required.
- **Conservative on invoice evidence.** Show what can be defended; don't
  inflate. Trust with clients is more valuable than a higher-looking number.
- **No expertise required.** Users should not need to understand token pricing,
  billing models, or allocation math to get value from the tool.

---

## Deliberately Out of Scope

- **Accounting system replacement.** Halyard produces invoice evidence and AI
  cost data. It does not replace QuickBooks, Xero, or expense management.
- **Prompt / code content logging.** Not in scope at any layer without an
  explicit, audited, opt-in feature with user consent.
- **Exact per-session cost for seat tools.** Tools like Copilot and Cursor Max
  don't expose per-call billing. Halyard allocates proportionally and labels it
  as such.
- **ROI claims.** Halyard captures AI spend, not AI outcome value. ROI
  calculations require user-defined outcome metrics that Halyard doesn't have.
- **Real-time budget enforcement** (blocking AI calls when a limit is reached).
  Alerting is a reasonable near-term feature; blocking is a different category
  with significant UX implications.

---

## Open Questions and Next Bets

These are the open questions as of May 2026 — not committed roadmap, but the
decisions that will shape v3 and beyond:

**Dynamic pricing sync.** The pricing table is snapshotted per release. Models
drop their prices constantly. A `halyard update-pricing` command that fetches
from a community-maintained source would keep costs accurate between releases.
The question is which source to trust and how to validate it.

**Budget alerts.** A per-project `daily_limit_usd` in `halyard.toml` with a
hook that warns when the limit is reached. The mechanism exists (hooks run
synchronously); the UX for "what happens when you hit the limit mid-session"
needs a spec.

**Git branch cost queries.** All sessions now carry `tags=branch:<name>`. The
data exists to answer "what did the auth-migration branch cost?" — but there's
no `halyard report --branch` command yet.

**Outcome attribution.** The next frontier after cost attribution is connecting
AI spend to delivered outcomes: features shipped, bugs fixed, PRs merged. This
requires either user-defined tagging or git integration deeper than branch names.

**Cloud sync and the enterprise path.** The org admin dashboard (v3) needs
cloud infrastructure for multi-user aggregation. The file format is ready. The
question is: managed service, self-hosted, or both?

---

## Feature PRDs

Detailed per-feature context lives in:

- [`PRD-ai-work-ledger.md`](PRD-ai-work-ledger.md) — the AI session ledger,
  plan costs, and attribution model (v1 / v2)
- [`PRD-local-activity-dashboard.md`](PRD-local-activity-dashboard.md) — the
  Glass Cockpit local dashboard (v2)
- [`PRD-org-admin-dashboard.md`](PRD-org-admin-dashboard.md) — org rollup,
  governance, and enterprise reporting (v3)

Feature PRDs are snapshots of the thinking at the time each capability was
conceived. They are not updated retroactively — the openspec change history is
the authoritative record of what was built and why.
