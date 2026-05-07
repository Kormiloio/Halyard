# Proposal: v1 — AI Intelligence Layer

## Why this change

v0 taught Halyard to track *human time* — when you started, when you stopped,
which project. That's necessary but no longer sufficient.

AI-assisted work has a second cost center that time tracking ignores: the AI
resources consumed in doing the work. Tokens, models, API spend. An hour of
Claude Opus and an hour of Haiku have the same clock duration and wildly
different costs. Neither shows up in `time.timeclock`.

This matters at every scale:

- **Solo developer/freelancer:** You're spending real money on API credits per
  client project. You can't invoice accurately, justify rates, or understand
  your margins without knowing what AI actually cost you on each engagement.

- **Engineering team:** The team lead can't answer "what did we spend on AI
  this sprint?" or "which projects are AI-heavy?" The data doesn't exist.

- **Enterprise (JPMC, Shell, GM):** The CTO cannot answer "what is our AI
  investment returning?" Finance cannot allocate AI costs to cost centers.
  Legal cannot audit what data went to which AI provider. None of the
  instruments exist.

Halyard v1 builds the instruments.

## What this change does

### 1. Define the AI session event schema (`ai-sessions.log`)

A new append-only plain-text file in the project directory. One line per AI
session (a bounded unit of AI work). Open format, human-readable,
git-diffable. Designed to be the hledger timeclock of AI usage — a stable,
public-spec format the broader ecosystem can build on.

### 2. Claude Code collector (the beachhead)

A Claude Code hook that auto-captures session data — start time, end time,
model, input/output tokens, calculated cost — and appends to
`ai-sessions.log` when a session closes. Zero friction for the user: start
working, the data appears.

### 3. Local analytics (`halyard report`)

CLI commands that read `ai-sessions.log` and `time.timeclock` together to
produce:
- Cost by project (AI spend attribution)
- Cost by model (understand your model mix)
- AI sessions over time
- Combined view: human hours + AI cost per project

This is the individual developer's instrument panel. It also proves the data
model before building the cloud layer.

### 4. API proxy collector (the unlock)

A local proxy that intercepts calls to `api.anthropic.com` and
`api.openai.com`, logs the usage event, and forwards the request
transparently. Works for any tool — Claude Code, Cursor, Copilot, scripts —
without code changes. This is what makes multi-tool capture possible.

## What this change does NOT do

- No cloud sync (that's v2)
- No team dashboard (that's v2)
- No enterprise multi-tenancy (that's v3)
- No changes to `time.timeclock` or the invoicing pipeline
- No new required dependencies for users who only want v0 features

## Architecture principle

**The collection protocol is the moat.**

`ai-sessions.log` and the collectors that write to it are open source (MIT,
same as everything else). Enterprise buyers can audit exactly what the agent
captures. The analytics and cloud layers built on top are where the business
model lives.

This mirrors the OpenTelemetry model: open instrumentation standard, proprietary
analytics on top. The difference is Halyard owns both sides.

## Two-audience invariant

Every decision in this change must satisfy both:

1. **Solo developer:** Works offline. No account. No setup beyond `halyard init`.
   Data is theirs, in their folder, forever.

2. **Enterprise buyer:** Data format is auditable, structured, and exportable.
   The cloud layer (v2) ingests `ai-sessions.log` without transformation.
   Nothing in v1 precludes adding SSO, multi-tenancy, or compliance in v3.

## Success criteria

- `cat ai-sessions.log` after a Claude Code session shows a correctly-formed
  entry with accurate token counts and cost
- `halyard report` shows AI spend by project in under 100ms on a 1-year log
- A developer can add the Claude Code hook in under 2 minutes with no config
- The data format spec is documented well enough that a third party could write
  a compatible collector
