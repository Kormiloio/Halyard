# PRD: Halyard

**Status:** Current public product PRD
**Last meaningful update:** May 8, 2026
**Companion:** [`current-direction.md`](current-direction.md)

---

## Status — May 8, 2026

Halyard has reached a working alpha:

- **Time tracking:** `halyard start/stop` and `halyard invoice` are
  functional for human time.
- **AI capture:** Collectors for **Claude Code**, **Cursor**,
  **Gemini CLI**, and **Codex App** are implemented with ambient project
  attribution.
- **Local visibility:** `halyard report`, `halyard dashboard`, `halyard tui`,
  and the REPL provide local visibility into human time, AI spend, model mix,
  and attribution state.
- **Data integrity:** Canonical serialization, malformed record quarantine,
  recoverable unattributed sessions, attribution provenance, and security
  hardening are active or in the current hardening track.
- **Ledger:** `halyard report --ledger` allocates API, seat, and credit plan
  costs by project with trust labels.

Current milestones:

1. Finish security/distribution hardening.
2. Finish log integrity and shared timer orchestration.
3. Harden cache, pricing, and invoice audit behavior.
4. Ship the attestable AI work appendix as the next proof-of-work artifact.
5. Defer outcome graph and org dashboards until design partners ask for them.

---

## What Halyard Is

Halyard is the open AI work ledger. It captures where AI-assisted work happens
- time, tokens, models, cost, project attribution, and trust metadata - and
turns that data into proof-of-work artifacts for individuals and AI Work
Intelligence for teams.

For the **solo developer or freelancer**: human time, AI spend, and invoice
evidence as plain text on your machine, operated by CLI. No account required.
Works offline. Data is yours, in your folder, forever.

For **small AI shops and teams**: shared evidence, client-safe appendices,
project spend, and trust-labeled cost allocation across multiple engineers.

For **future enterprise buyers**: governance, cost centers, redacted sync, and
effectiveness analytics across tools - built on the same local data format, but
only after the local proof artifact and security posture are credible.

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

**The trusted local ledger is the moat.**

`ai-sessions.log` and the collectors that write to it are open source (MIT).
Enterprise buyers can audit exactly what the agent captures. The analytics and
cloud layers built on top are where the business model lives.

The protocol story should be earned by adoption. Halyard can publish stable
formats, fixtures, and examples, but a public `ai-sessions.log` spec becomes
strategic only after at least one external emitter exists.

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
| v1.5 | Multi-Tool Collectors | Capture AI work across Claude, Cursor, Gemini, Codex | Shipped |
| v2 | AI Work Ledger + Dashboard | What did AI-assisted work cost per project? | Shipped |
| v2.16-v2.22 | Hardening Track | Can the local ledger survive real use and review? | Active |
| v2.19 | Attestable Appendix | Can I prove AI-assisted work to someone else safely? | Next |
| v3.0 | Outcome Graph | Did AI-assisted work connect to outcomes? | Gated |
| v3+ | Org Intelligence | What is the org getting from AI investment? | Deferred |

Each layer depends on the previous. The local ledger must be trustworthy before
it can become a shareable proof artifact. The proof artifact must create user
pull before org rollups or outcome analytics deserve more surface area.

---

## Core Concepts

### Human time
The clock time a person spends directing, reviewing, building, communicating,
and making decisions on a project. Stored in `time.timeclock` (hledger timeclock
format). Tracked with `halyard start / stop`.

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
1. Active timer (`halyard start acme:auth`)
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
4. **Append-only direction, with today's carve-out documented.** New sessions
   are always appended. Attribution corrections (assigning an unattributed
   session to a project via `halyard assign-unattributed`) may currently
   atomically rewrite the log to update the `project=` field. No captured data
   is discarded; only metadata is corrected. The active hardening track moves
   this toward explicit correction records.
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
decisions that shape the current hardening and proof-of-work wedge:

**Attestable appendix.** The next network-effect feature is a signed,
verifiable AI work appendix. It should let a recipient verify that an invoice
appendix was not modified, while preserving the privacy contract: no prompts,
no code, no file contents.

**Pricing table trust.** Dynamic pricing is useful, but it cannot silently
overwrite a trusted local table. The current question is how to make
`halyard update-pricing` fail closed on suspicious changes while keeping first
setup simple.

**Append-only correction records.** Attribution cleanup currently exists, but
the durable trust story improves when corrections become explicit amendment
records instead of in-place rewrites.

**Design-partner pull.** Outcome graph, duplicate-effort detection, org
dashboards, and redacted sync are not gone. They are gated until design
partners ask for them and the local proof artifact has been tested in the
field.

**External emitters.** A public `ai-sessions.log` spec should follow at least
one external tool emitting the format. Specs without adoption are not enough.

---

## Feature PRDs

Detailed per-feature context lives in:

- [`current-direction.md`](current-direction.md) — current public product
  direction and build sequence
- [`PRD-ai-work-ledger.md`](PRD-ai-work-ledger.md) — the AI session ledger,
  plan costs, and attribution model (implemented baseline)
- [`PRD-local-activity-dashboard.md`](PRD-local-activity-dashboard.md) — the
  Glass Cockpit local dashboard (implemented local surface)
- [`PRD-org-admin-dashboard.md`](PRD-org-admin-dashboard.md) — org rollup,
  governance, and enterprise reporting (deferred / design-partner gated)

Feature PRDs are snapshots of the thinking at the time each capability was
conceived. When they disagree with `current-direction.md`, the current
direction doc and active OpenSpec changes win.
