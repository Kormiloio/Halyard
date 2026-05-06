# Halyard — Project Context

This file is loaded by OpenSpec on every change. It establishes shared
conventions so each change proposal doesn't have to re-explain them.

## Mission

Halyard is AI work intelligence infrastructure. It captures where AI work
happens — time, tokens, models, cost, project attribution — and turns that
data into actionable intelligence for individuals and organizations alike.

For the solo developer or freelancer: time, AI spend, and invoices as plain
text on your machine, operated by Claude. For engineering teams and
enterprises: unified visibility into AI investment, productivity, and cost
allocation across the organization.

The individual experience is the entry point. The enterprise layer is
optional, additive, and built on the same open data format. An AI agent
(Claude) reads and writes the files on the user's behalf at every tier.

## Non-negotiables

These constraints apply to every change. Any proposal that breaks them needs
to explicitly justify the exception.

1. **Local-first.** No required cloud service. Optional paid tiers may exist
   later for sync or e-filing, but the core product runs offline against a
   local folder.
2. **Plain text forever.** All user data is stored in human-readable,
   diff-friendly text formats with public specs:
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
5. **MIT licensed.** Permissively. Forever.

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

`ai-sessions.log` is append-only, plain text, open format — the same
local-first guarantee as `time.timeclock`. The cloud sync and enterprise
layers read from this file; they do not replace it.

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
