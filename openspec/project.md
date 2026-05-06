# Halyard — Project Context

This file is loaded by OpenSpec on every change. It establishes shared
conventions so each change proposal doesn't have to re-explain them.

## Mission

Halyard is a plain-text, agent-native financial OS for freelancers and
one-person businesses. Time, expenses, clients, projects, and invoices live
as plain-text files on the user's machine. An AI agent (Claude) reads and
writes those files on the user's behalf.

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
├── time.timeclock        # hledger timeclock format
├── ledger.beancount      # Beancount ledger (added in v1)
├── invoices/             # generated invoice .md and .pdf files
├── expenses/             # raw bank/receipt CSVs (added in v1)
├── templates/            # optional user overrides
│   └── invoice.md.j2
└── .gitignore
```

Per-user agent state (skills, API keys, active timer) lives in
`~/.halyard/`, not in the project folder.

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
