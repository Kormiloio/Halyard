# PRD: Halyard

**Status:** Current public product PRD
**Last meaningful update:** May 9, 2026
**Companion:** [`current-direction.md`](current-direction.md)

---

## Status — May 9, 2026

Halyard has reached a working alpha with a full security hardening track complete
and is preparing for an OSS community launch (HN / Reddit / Lobsters).

**What is shipped:**
- **Time tracking:** `halyard start/stop` and `halyard invoice` are functional.
- **AI capture:** Collectors for **Claude Code**, **Cursor**, **Gemini CLI**,
  and **Codex App** with ambient project attribution and file locking, plus
  **VS Code/Copilot** manual capture through a local VS Code task.
- **Local visibility:** `halyard report`, `halyard dashboard`, `halyard tui`,
  and the REPL.
- **Data integrity:** Append-only correction records, file locking, attribution
  provenance, and 13 AppSec findings remediated.
- **Ledger:** `halyard report --ledger` allocates API, seat, and credit plan
  costs by project with trust labels.
- **Test suite:** 52 test files, green on HEAD, mypy strict + ruff clean.

**Current milestones (in order):**

1. Finish cache, pricing, and invoice audit hardening (v2.18).
2. OSS community launch — get real users, validate the format.
3. Outcome-aware metadata uplift: branch as first-class field, commit count,
   code delta across all collectors, PR linkage (v2.24 — moves score 2/10 → 6/10).
4. Attestable AI work appendix: signed, verifiable proof-of-work artifact (v2.19).
5. Outcome graph only when design partners ask for it (v3.0, gated).

**Strategic sequence:** users and trust before paid tiers. No paid features are
discussed in any OSS-facing surface until the community has validated the format.

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
Gemini CLI, VS Code/Copilot, and API calls. But:

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

**OSS-first. Trust before paid tiers.**

The entry point is an individual developer who installs Halyard because they
want it — not because a manager asked them to. That install happens because
the developer trusts that Halyard is open, local, and honest. Trust comes
from the community (HN, Reddit, Lobsters) validating the concept before any
commercial motion starts.

The sequence is: trust → users → community → then paid. Any attempt to flip
that order kills bottoms-up adoption. Paid tiers are real and will exist, but
they must never appear in OSS-facing surfaces — README, CLI help, or any
community post — until the community has validated the format.

**The trusted local ledger is the moat.**

`ai-sessions.log` and the collectors that write to it are open source (MIT).
The analytics and cloud layers built on top are where the business model lives,
but only after the local product has earned adoption.

The protocol story should be earned by adoption. A public `ai-sessions.log`
spec becomes strategic only after at least one external emitter exists. Specs
without adoption are vanity docs.

The plaintext files are the durable asset. A future in which ten tools write
compatible `ai-sessions.log` entries — and Halyard is the analytics layer — is
a better outcome than a future in which Halyard is the only tool that can capture.

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
| v2.27 | VS Code Manual Capture | Track VS Code/Copilot work through editor tasks | Shipped |
| v2 | AI Work Ledger + Dashboard | What did AI-assisted work cost per project? | Shipped |
| v2.16-v2.23 | Hardening Track | Can the local ledger survive real use and review? | Shipped |
| v2.18 | Cache + Audit Hardening | Is the local cache stable enough to rely on? | Active |
| OSS Launch | Community Release | Do real users trust and use the format? | Next |
| v2.24 | Outcome Metadata | Does each session carry branch, commits, code delta, PR? | Shipped |
| v2.19 | Attestable Appendix | Can I prove AI-assisted work to someone else safely? | Gated on v2.24 |
| v3.0 | Outcome Graph | Did AI-assisted work connect to outcomes? | Design-partner gated |
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

Since v2.28, Halyard also records human time automatically while Claude Code is
active. The **auto human timer** uses a presence-window model: one `i`/`o`
timeclock block per contiguous work session, regardless of how many AI turns it
contains. A session is considered ended when more than 30 minutes pass since the
last Claude Code hook event. Auto entries carry a `;auto` comment so they are
distinguishable from manual `halyard start / stop` entries. A manual timer
always takes precedence — the auto-timer silently skips when one is running.

### AI session
A bounded unit of AI tool activity: a Claude Code session, a Cursor stop event,
a Gemini CLI turn, a Codex Desktop session, a VS Code/Copilot manual capture, or
a direct API call. Stored as one line in `ai-sessions.log`. Fields: start, end,
tool, model, input tokens, output tokens, cost, and optional key=value pairs for
project, branch, cache, billing model, and more.

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
- Tool slug (`claude-code`, `cursor`, `gemini-cli`, `codex`, `vscode`, etc.)
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
| VS Code / GitHub Copilot | VS Code task + `record-session --tool vscode`; no public Copilot hook yet | Manual capture shipped |
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

## Email Integration (Deferred)

Three distinct email capabilities are planned but not yet scheduled:

### 1. Email session capture
Some AI-assisted work happens in email: prompting via Gmail, iterating on a
draft with Claude, or using an AI email assistant. A future `halyard
import-email` command (or a Gmail / Outlook hook) would ingest these
interactions as sessions in `ai-sessions.log`, attributed by thread or label.
This is distinct from the existing collectors — email sessions are identified
by message timestamps and subject, not tool stop events.

### 2. Invoice and report delivery
`halyard invoice` already generates a PDF; a future `halyard send-invoice`
command would attach it to an outbound email via SMTP or a mail provider
(SendGrid, Mailgun, or native macOS Mail). The same pipeline could deliver
weekly or monthly summary reports to a client or manager address on a schedule.

### 3. Meeting time capture via calendar email
AI-adjacent meetings (standups, design reviews, client calls scheduled via
email invites) represent human time that is currently untracked. A future
`halyard import-calendar` command would parse iCal / ICS export files or sync
with Google Calendar / Outlook Calendar API to pull meeting events into
`time.timeclock` as clock-in/out blocks, tagged `;calendar`.

All three capabilities share a dependency on an authenticated outbound/inbound
mail credential that Halyard does not yet manage. They are deferred until the
core ledger and OSS install base are established.

---

## Pre-Ship Hardening (v2.29)

A pre-launch architecture and security review on 2026-05-10 identified seven
issues that must be resolved before the public OSS release. All seven are
addressed in v2.29. Full spec: `openspec/changes/v2.29-pre-ship-hardening/`.

### 1. Windows platform safety
`fcntl` is a POSIX-only module. Halyard will not be installed on Windows without
a platform guard. v2.29 adds a no-op lock fallback for Windows with a clear
error message, macOS/Linux OS classifiers in `pyproject.toml`, and a README note
directing Windows users to WSL2.

### 2. TOML injection
`voyages.py` and `git_context.py` built TOML files using unescaped f-string
interpolation. A project slug containing a double-quote or newline could corrupt
or structurally modify these config files. Fixed by replacing all manual TOML
construction with `tomli_w.dumps()`, which correctly escapes all string values.

### 3. Pricing hash bypass
`halyard update-pricing` called `_check_pricing_hash()` but discarded its return
value. A changed pricing table was accepted silently after a stderr warning. For
a tool that calculates client bills, silent pricing changes are a billing
integrity failure. Fixed: changed hash now requires explicit user confirmation
or the `--accept-changed` flag. Non-interactive environments abort by default.

### 4. Outcome hash mismatch
`_session_line_hash()` in `outcomes.py` hashed the serialized form of an
already-mutated `AiSession` (one with amendments folded in), producing a hash
that no `a` record in the log references. Outcome amendments silently failed to
round-trip. Fixed by carrying `_raw_hash` on `AiSession` — set from the
original `s` line before any amendment folding — so the hash is always stable.

### 5. SQLite cache staleness
`db.py` used `INSERT OR IGNORE` when syncing sessions, meaning sessions that
received amendments after the initial sync (attribution changes, PR linkage) were
never updated in the cache. `halyard report --from-cache` silently served stale
data. Fixed: changed to `INSERT OR REPLACE` so re-running `halyard db sync`
always brings the cache into agreement with the log.

### 6. Datetime timezone inconsistency
`claude_code.py` stored session start in UTC while all other collectors used
local time. Both landed as timezone-naive datetimes in `AiSession`, making
day-boundary comparisons wrong for non-UTC users near midnight. Fixed by
standardizing all collectors to local-naive time, consistent with the timeclock
file format and the user's mental model.

### 7. OS declaration
`pyproject.toml` had no OS classifiers and the README had no platform note.
Windows users discovered the `fcntl` crash only after installation. Fixed by
adding POSIX/macOS classifiers and a platform note to the README install section.

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
decisions that shape the current work.

**OSS community launch.** The gate is `pipx install halyard && halyard init`
working end-to-end with zero friction in a clean venv. Once that passes smoke
test, the HN / Reddit / Lobsters post goes out. The goal is not stars — it is
comments from people who installed it and it worked.

**Outcome-aware metadata (v2.24) — shipped.** Branch is now a first-class
`AiSession` field, commit count and code delta are captured by all four
collectors, and `halyard outcome sync` resolves PR linkage via `gh`. The
outcome score moves from 2/10 to 6/10. The `halyard report --outcomes` and
`halyard outcome report` commands bucket sessions by PR state (shipped /
in-flight / abandoned / no PR). Amendment records in `ai-sessions.log` carry
pr_ref and pr_state; the SQLite cache (v3 schema) indexes them for fast
queries.

**Attestable appendix (v2.19).** The next network-effect feature is a signed,
verifiable AI work appendix — a recipient verifies without seeing prompts or
code. Gated on v2.24 landing so the appendix can include commit and PR signals.

**Pricing table trust.** `halyard update-pricing` should fail closed on
suspicious changes. Stays open until v2.18 delivers the schema migration
framework.

**Design-partner pull.** Outcome graph, duplicate-effort detection, org
dashboards, and redacted sync are gated until at least one design partner asks
for them and the OSS install base has validated the format.

**External emitters.** The `ai-sessions.log` spec is published only after at
least one external tool emits the format. Specs without adoption are not enough.

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
