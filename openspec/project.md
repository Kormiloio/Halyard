# Halyard — Project Context

This file is loaded by OpenSpec on every change. It establishes shared
conventions so each change proposal doesn't have to re-explain them.

## Mission

Halyard is the open AI work ledger. It captures where AI-assisted work happens
- time, tokens, models, cost, project attribution, and trust metadata - and
turns that data into proof-of-work artifacts for individuals and AI Work
Intelligence for teams.

For the solo developer, freelancer, or small AI shop: time, AI spend, project
attribution, and invoice evidence as plain text on your machine. The near-term
wedge is proving AI-assisted work without exposing prompts or source code.

For teams and enterprises: the same ledger can later support redacted sync,
governance, cost centers, and cross-tool AI Work Intelligence. That layer is
additive and gated on design-partner pull plus security readiness.

The individual experience is the entry point. The enterprise layer is
optional, additive, and built on the same open data format.

## Non-negotiables

These constraints apply to every change. Any proposal that breaks them needs
to explicitly justify the exception.

1. **Local-first.** No required cloud service. Optional paid tiers may exist
   later for sync or e-filing, but the core product runs offline against a
   local folder.
2. **Plain text forever.** All user data is stored in human-readable,
   diff-friendly text formats. Use existing public specs where they already
   exist; publish Halyard-owned specs after the local format has proven useful
   and at least one external emitter exists:
   - Time → [hledger timeclock](https://hledger.org/timeclock.html)
   - Ledger → [Beancount](https://beancount.github.io/)
   - Invoices → markdown with YAML frontmatter
   - Config → TOML
   No proprietary formats. No SQLite-as-source-of-truth.
3. **Files are the source of truth.** Any UI (CLI, web, future GUI) is a
   view onto the files. The agent edits the same files a human would.
4. **No silent writes.** Any modification to user data is proposed to the
   user with a diff and waits for approval. Read-only operations need no
   approval.
5. **No prompt or source-code capture by default.** Halyard captures metadata,
   not transcripts, prompts, file contents, or code context.
6. **Trust labels over fake certainty.** Reports distinguish captured,
   calculated, allocated, inferred, missing, and mixed data.
7. **MIT licensed.** Permissively. Forever.

## Project layout (per Halyard project)

A user's Halyard project directory contains:

```
my-business/
├── halyard.toml          # business name, currency, invoice counter
├── clients.toml          # array of clients
├── projects.toml         # array of projects (linked to client_slug)
├── time.timeclock        # hledger timeclock format (human time)
├── ai-sessions.log       # AI usage events: tokens, model, cost (added in v1)
├── ledger.beancount      # Beancount ledger (added in v2)
├── invoices/             # generated invoice .md and .pdf files
├── expenses/             # raw bank/receipt CSVs (added in v2)
├── templates/            # optional user overrides
│   └── invoice.md.j2
└── .gitignore
```

Per-user agent state (skills, API keys, active timer) lives in
`~/.halyard/`, not in the project folder.

`ai-sessions.log` is plain text, open format — the same local-first guarantee
as `time.timeclock`. New sessions are always appended. The current hardening
track is moving attribution corrections toward explicit correction records so
the open log can become genuinely append-only. Cloud sync and enterprise layers
must read from this local source of truth; they do not replace it.

## Active focus (May 2026)

- **Security and distribution hardening:** dashboard write safety, packaged
  templates, dependency audit, launch-readiness checks.
- **Log integrity:** locking, correction records, shared timer orchestration,
  and active-file race cleanup.
- **Cache and audit hardening:** SQLite read-model reliability, pricing table
  integrity, invoice audit schema, and config-history robustness.
- **Attestable AI work appendix:** signed, verifiable, client-safe proof of
  AI-assisted work. This is the current network-effect feature.
- **Design-partner validation:** outcome graph and org rollups are gated until
  real users ask for them.

## Deferred or gated

- Org admin dashboards, SSO/RBAC, and hosted enterprise reporting wait until
  security posture and design-partner pull justify them.
- Outcome graph work waits until at least one design partner asks to connect
  AI sessions to commits, PRs, tests, and delivered outcomes.
- Calendar scheduling and new collectors beyond the current core set are not
  current wedge work.

## Stack defaults

- **Language:** Python 3.11+
- **CLI:** Typer + Rich
- **Models:** Pydantic v2
- **Templating:** Jinja2
- **PDF:** typst (subprocess)
- **Time parsing:** dateparser
- **Agent:** Anthropic SDK with tool use (single-turn loop in v0)
- **Tests:** pytest with golden-file tests for renders
- **Lint/format:** ruff

Any deviation from this stack needs justification in the change's `design.md`.

## How changes work

Each change lives at `openspec/changes/<change-slug>/` with:

- `proposal.md` — why & what's changing (high level)
- `specs/*.md` — requirements with scenarios, in WHEN/THEN form
- `design.md` — technical approach, choices, trade-offs
- `tasks.md` — the implementation checklist

Completed changes get archived to `openspec/changes/archive/YYYY-MM-DD-<slug>/`.

## Spec-first rule

**Write the spec before writing the code.**

For any non-trivial change (new command, new collector, new concept):

1. Create the change directory and write `proposal.md` first.
2. Get alignment on the proposal before writing `design.md` and `specs/`.
3. Only then open code. `tasks.md` is the bridge — write it before starting
   implementation, check items off as you go.

What counts as non-trivial: anything that adds a new user-facing command,
introduces a new file or data format, changes existing behaviour in a
way that affects stored data, or requires design decisions with trade-offs.

Bug fixes, test additions, and internal refactors that don't change the
observable contract are exempt — do those directly.

The purpose of spec-first is not process for its own sake. It's to ensure
the "why" is captured while it's fresh, so future contributors (and future
AI assistants) can understand intent, not just implementation.
