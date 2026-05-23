# PRD: Halyard AI Work Ledger

**Status — May 8, 2026:**
Implemented baseline. This PRD describes the ledger wedge that is now largely
shipped: AI session capture, plan allocation, reports, dashboard visibility,
invoice evidence, and trust labels. It remains useful background, but it is not
the active roadmap. See [`current-direction.md`](current-direction.md) for the
current hardening and attestable-appendix sequence.

---

## Summary

Halyard should become the local-first ledger for AI-assisted work: human time,
AI time, token usage, model mix, plan/seat costs, API spend, and project
attribution, all captured where the work happens and stored in plain text.

The existing freelancer time, expense, and invoicing workflow remains the first
user experience. The strategic shift is that Halyard is not only an invoicing
assistant. It is the instrument panel for modern AI labor.

## Problem

Freelancers and teams are now hired to produce outcomes with AI. A client may
hire Mario to build an auth migration, a prototype, or an internal automation,
and the real work is a mix of:

- human judgment and project direction;
- Claude Code, Codex, Cursor, Gemini CLI, VS Code/Copilot, API calls, and other
  AI tool sessions;
- token consumption and model selection;
- subscription seats, credits, and API invoices;
- project-specific artifacts, plans, prompts, and implementation sessions.

Current time trackers only capture the human clock. Finance tools only see
monthly vendor bills. AI tools expose usage in different places, if they expose
it at all. Nobody can answer, with local evidence:

- How much human time did this project take?
- How much AI work did it consume?
- Which models and tools were used?
- What did it cost in API usage, credits, and seats?
- What should be passed through, marked up, or absorbed?
- What evidence supports the invoice?

## Product Thesis

The cool part of Halyard is not the invoice CLI. The cool part is a
user-owned ledger of AI labor and AI spend.

Halyard should make the local product useful first, then earn the right to
publish broader specs and business layers on top. The plaintext files are the
durable asset. The CLI, reports, local activity dashboard, attestable appendix,
and future sync are views over that asset.

## Goals

- Capture AI-assisted work as a first-class ledger beside human time.
- Attribute AI usage to clients, projects, tasks, and eventually deliverables.
- Support API, credit, and seat-based billing models.
- Let freelancers turn AI usage into invoice evidence and margin analysis.
- Let teams aggregate the same data into cost allocation and productivity
  intelligence.
- Keep the solo developer flow local-first, offline-capable, and plain text.
- Make the data format open enough that other tools can write compatible
  collectors.

## Non-Goals

- Replace accounting systems in the first version.
- Require cloud sync or an account.
- Guarantee exact per-session cost for tools that only expose monthly seat
  pricing.
- Capture private prompt or code content by default.
- Build an enterprise dashboard before the local data model proves itself.

## Primary Users

### AI-assisted freelancer

Mario is hired to build software using AI-heavy workflows. He wants to know
what each client project consumed in human time and AI resources, then generate
an invoice with defensible detail.

### Solo consultant with multiple AI plans

A consultant pays for Claude, ChatGPT, Cursor, and API credits. They need to
understand which clients or projects justify those subscriptions.

### Engineering lead

A lead wants to understand AI investment by project, team, model, and time
period without relying on each vendor dashboard.

### Finance / operations buyer

Finance needs cost allocation and auditability for AI spend. They need a clean
source of truth that can be exported or synced.

## Core Concepts

### Human time

The clock time a person spends directing, reviewing, building, communicating,
and making decisions. Stored in `time.timeclock`.

### AI session

A bounded unit of AI tool activity: a Claude Code session, Codex session, API
proxy window, Cursor operation, Gemini CLI turn, VS Code/Copilot manual entry,
or agentic job segment. Stored in `ai-sessions.log`.

Since v3.5, Claude Code sessions include an advisory **client surface** tag
(`cli`, `desktop`, `ide`, or `unknown`) to distinguish between different tool
launchers. This is a heuristic derived from the local environment, labeled as
such in all reports, and is used to provide deeper visibility into how
multi-interface tools are lean on for different types of work.

### AI work unit

A higher-level aggregation of one or more AI sessions that belong to a task,
plan, deliverable, or job. This may be represented by `job_id`, `task_id`, or
future record types.

### Token contract (v2.62)

Every collector emits `input_tokens` as **fresh, non-cached input
only**. Cached tokens live solely in `cache_read` / `cache_write`; no
token is ever counted in both. Cost is then `input × 1.0× +
cache_read × read_mult + cache_write × write_mult`, so a cached token
is never billed at both the full input rate and the cache rate.

Per-collector semantics (audited v2.62):

- **claude_code / cursor** — receive the Anthropic usage schema, where
  `input_tokens` is natively *exclusive* of cache; `cache_read` and
  `cache_write` are separate, disjoint counts. Both already capture
  `cache_write` (Anthropic `cache_creation_input_tokens`).
- **gemini_cli / codex_app** — the source reports *gross* prompt input
  (the cached subset is included). Halyard subtracts the cached tokens
  at capture so the stored `input_tokens` is fresh-only.
- **`cache_write` is structurally unavailable for Gemini and Codex** —
  neither tool's payload/transcript exposes a cache-*creation* token
  field, so `cache_write` is correctly `None` (unavailable is not
  zero), and their cost simply omits the cache-write term.

**Documented pre-v2.62 history caveat:** Halyard never billed cached
Gemini/Codex tokens twice (the subtraction predates v2.62), but
because those tools expose no cache-creation signal, any pre-v2.62
Gemini/Codex line still under-counts cache *writes* — there is no
cache-write data to recover. History is immutable and is **not**
retro-corrected; only capture going forward is governed by this
contract.

### Session time capture (v2.67)

`wall_seconds` and `agent_active_seconds` are captured as before
(unchanged). Two additional **independent optional** fields,
`api_seconds` and `tool_seconds`, hold true, *measured* api- and
tool-call time for **Gemini CLI** only, sourced from the user's
**opt-in** OpenTelemetry outfile (`telemetry.target:"local"` +
`telemetry.outfile`). Capture is opt-in and explicit
(`halyard install-gemini-telemetry` proposes the config; `halyard
doctor` nudges, warn-only, when the Gemini hook is on but telemetry
is off). Privacy is capture-only: solely `duration_ms`, the event
name, and the resource `session.id` are read — never prompt,
response, or tool-argument content, even when the user set
`logPrompts:true`. Unavailable (telemetry off, no outfile, no
matching session) is `None`, never `0` — never estimated. These
fields are additive and backward compatible; `agent_active_seconds`
is **not** converted or removed (the breaking change v2.63 specced
is explicitly rejected).

### Plan and entitlement cost

Costs that are not naturally per-token: Claude Max, ChatGPT Plus/Team, Cursor
credits, Copilot seats, Devin/Factory credits, or enterprise contracts.

### Attribution

Mapping human time and AI usage to `client:project`, plus optional task,
deliverable, user, tool, model, and billing metadata.

The slug is semantically `payer:work-unit` — the left side is *whoever
bears the cost of the work*, not specifically an external customer.
For a freelancer that is a client they bill; for an internal team it
is a cost center / initiative whose AI cost and ROI they measure. The
captured primitive is identical; only the consumer of the
attribution differs (external invoice vs. internal cost/ROI). Halyard
OSS keeps the slug a simple opaque `namespace:unit` label and does
not interpret organizational hierarchy — cost-center rollups,
chargeback/showback, and ROI reporting are an additive
**Halyard-Enterprise** layer over the same ledger, gated on
design-partner pull, never a fork of the OSS capture model.

## MVP Scope

The MVP should answer:

> For this client project, how much human time and AI resource usage went into
> the work, and what did it cost?

Required capabilities:

- Capture Claude Code sessions automatically into `ai-sessions.log`.
- Track active project attribution from `halyard start`.
- Record token counts, model, cache tokens, cost, and source.
- Support manual plan/seat cost configuration for tools with subscriptions.
- Produce a local report combining human hours and AI usage by project.
- Run a local dashboard showing the active timer, recent AI sessions, collector
  health, and cost attribution as work happens.
- Show margin inputs: human billable amount, AI cost, and AI cost percentage.
- Export invoice evidence as markdown.
- Emit a standalone AI-work evidence artifact (`halyard evidence`, v2.68)
  for any deliverable — not just invoices — reusing the same appendix
  renderer, with a deterministic keyless `sha256:` integrity digest.
  The digest is tamper-evident (re-hashable by anyone via
  `halyard evidence --verify`) but is explicitly not a signature and
  not authorship proof; cryptographic attestation is a Halyard
  Enterprise feature (the moved v2.19), out of OSS scope.

## JSON output (v2.69)

`report`, `usage`, `budget`, `status`, `evidence`, `health`, and
`doctor` accept `--json` (health uses `--format json`), emitting a
single JSON object/array via one shared `jsonio` seam: datetimes are
ISO 8601, `Path` is a string, private (`_`) fields are omitted, and
`--json` suppresses all human/Rich output. Errors are still emitted
as `{"error": "..."}` with a non-zero exit so a script never has to
parse prose. The schema is **semi-stable and additive-only**: new
keys may appear; existing key names/types do not change without a
note here. No published JSON Schema file until an external consumer
exists. `evidence --json` is structured metrics with **no digest** —
the v2.68 integrity digest is defined over the markdown artifact
only; the JSON form is unsigned data.

## Later Scope

- API proxy collector for Anthropic, OpenAI, Gemini, and OpenRouter (deferred;
  no new collectors until the current hardening track is complete).
- SDK wrappers for scripts and internal tools.
- ~~Tool-specific collectors for Codex, Cursor, Devin, Factory, and other AI
  work surfaces.~~ **Shipped (v1.5):** Codex, Cursor, and Gemini CLI collectors
  are live. **Shipped (v2.27):** VS Code/Copilot can be tracked through
  `halyard install-vscode-tasks` and `record-session --tool vscode` as manual
  capture because Copilot does not expose a public session-end hook or token
  payload. Native Copilot, Devin, Factory collectors remain future work.
- ~~Plan allocation rules: by session count, active minutes, project weight, or
  manual allocation.~~ **Shipped (v2):** `ai-plans.toml` + `halyard report --ledger`.
- ~~Deduplication across tool-wraps-tool scenarios.~~ **Shipped (v1.5):** The
  `cursor_version` guard in the Claude Code collector prevents double-recording.
- Team sync and dashboard (deferred until design-partner pull and security
  readiness).
- Compliance/audit exports.
- Outcome-based billing support (gated on outcome-graph demand).
- **Outcome graph as the ROI through-line (v3.0, gated).** Linking
  sessions to commits/PRs/tests is the same primitive at every scale:
  for a freelancer it answers "did this AI work ship?"; rolled up over
  cost centers it answers the enterprise question "is our AI spend
  producing delivery, and where?". Same captured data, additive
  Halyard-Enterprise consumer — not an OSS scope expansion.
- **Extensible log contract (v2.75, proposed).** The `ai-sessions.log`
  line grammar + `--json` schema are the stable, versioned
  integration surface third-party and Halyard-Enterprise consumers
  build on; unknown tokens are preserved (not dropped) so the format
  can be extended without forking the OSS parser. See
  `docs/integration-contract.md`.

## Key User Stories

- As a freelancer, I can start work on `acme/auth-migration`, use Claude Code,
  stop work, and see both my human time and AI cost attributed to ACME.
- As a freelancer, I can configure my Claude Max, ChatGPT, Cursor, or Copilot
  plan cost and have Halyard allocate a reasonable project share.
- As a VS Code/Copilot user, I can run a local VS Code task after an AI-assisted
  work block and have that session appear in reports, dashboard usage, and my
  Passport without exposing prompt or code content.
- As a consultant, I can show a client a concise invoice appendix listing AI
  tools, models, sessions, and cost without exposing private prompts.
- As an engineering lead, I can summarize AI spend by project and model for a
  sprint.
- As a future enterprise admin, I can sync the same local records into a
  central system without changing their meaning.

## Data Principles

- Plain text is the source of truth.
- Usage records should move toward append-only correction records. Today,
  attribution corrections via `halyard assign-unattributed` are the one
  permitted atomic rewrite; no captured data is discarded.
- Unknown fields are ignored by old parsers.
- Captured cost is snapshotted at the time of capture.
- Sensitive content is opt-in, not default.
- Local project data and per-user state remain separate.
- Reports may derive allocations, but raw logs should not be rewritten.

## UX Principles

- The best capture is invisible: users do the work and the ledger fills in.
- The user should not have to become a usage-accounting expert.
- Reports should explain uncertainty, especially with seat and credit costs.
- The local dashboard should make invisible capture visible without becoming a
  required cloud product.
- Invoice evidence should be clear enough for clients and conservative enough
  for trust.
- The CLI should stay fast and terminal-native.

## Success Metrics

- A new user can initialize Halyard, install the Claude Code hook, and capture
  the first AI session in under two minutes.
- A VS Code/Copilot user can install the local VS Code task and manually capture
  a Copilot work block without learning the raw `ai-sessions.log` format.
- `halyard report` can answer human hours plus AI spend by project in under
  100ms for a one-year local log.
- A freelancer can generate an invoice appendix with human hours, AI sessions,
  model usage, and total AI cost.
- The file format is clear enough for a third party to implement a compatible
  collector.
- The README demo makes the AI work ledger obvious within the first minute.

## Open Questions

Some of these questions have since been answered by implementation. Remaining
questions should be interpreted through the current direction doc.

- Should plan/seat costs live in `halyard.toml`, `plans.toml`, or per-user
  `~/.halyard/config.toml`?
- What allocation rule should be the default for monthly seats: session count,
  active minutes, token-equivalent weight, or manual allocation?
- Should invoice appendices include AI cost as pass-through, markup, internal
  margin evidence, or all three?
- How should Halyard capture AI work from Codex specifically? **Answered:**
  Codex Desktop imports JSONL sessions.
- What public API or extension hook, if any, should upgrade VS Code/Copilot from
  manual task capture to automatic per-session/token capture?
- When should a sequence of AI sessions become one higher-level AI work unit?
- How much project/task context should be captured without risking sensitive
  content exposure?
