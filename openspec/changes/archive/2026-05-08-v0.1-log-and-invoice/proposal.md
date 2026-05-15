# Proposal: v0.1 — Close v0: `halyard log` and `halyard invoice`

## Why this change

`halyard log` and `halyard invoice` are the two most prominent user-facing
commands in the Halyard CLI. Both currently raise `NotImplementedError`. They
are displayed in `halyard --help`, referenced in the README quickstart, and
represent the core promise of the v0 product tier — "AI reads and writes your
work data on your behalf."

Three independent AI tool evaluations of the project identified closing this gap
as the single highest-priority item. The collection stack (v0 through v2.3) is
solid. The log fills in correctly. But users cannot query that log, and they
cannot convert captured time into an invoice.

This change closes v0 completely.

## What this change does

### `halyard log`

Implements a provider-neutral log query layer. The default `local` provider is
deterministic, offline, and queries the same local Halyard files as any future
model-backed provider. Claude is the first planned model-backed provider, but
it is a reasoning engine only; it does not define which captured tools can be
queried.

The query layer receives:

- System context: project config, current budget state, pricing table metadata
- Contents of `ai-sessions.log` (or hub log if outside a project directory)
- Natural language query from the user

The command returns a typed `LogQueryResponse` object — not free-form text. The
CLI renders the structured response as a Rich table or paragraph. With `--json`,
the raw response is emitted for piping.

Tools available to the agent:
- `read_sessions(project?, start?, end?)` — filtered view of ai-sessions.log
- `summarize_by_project(start?, end?)` — cost and token totals per project
- `summarize_by_model(start?, end?)` — cost and token totals per model
- `cost_by_branch(branch)` — sessions tagged with a given branch name
- `read_timeclock(start?, end?)` — human time entries from time.timeclock

No prompt content is ever read. Providers only have access to metadata log
files. The local provider sends nothing to a network service.

### `halyard invoice`

Reads `time.timeclock`, `clients.toml`, `projects.toml`, and `halyard.toml` to
render a Jinja2 invoice. Steps:

1. Validate: client slug must exist in `clients.toml`, project slug must exist
   in `projects.toml`.
2. Read closed time entries (clock-out recorded) for the specified project in
   the given billing period. Warn if any open entries exist.
3. Render invoice markdown using `templates/invoice.md.j2` (bundled default or
   user override).
4. Increment `invoice_counter` in `halyard.toml` atomically (read-modify-write).
5. Write to `invoices/YYYY-MM-{counter:03d}-{client}.md`.
6. If `--pdf` is passed, run `typst compile` as a subprocess to produce a PDF
   alongside the markdown. Degrade gracefully if typst is not installed.
7. Optionally include AI session cost breakdown as a line item when
   `include_ai_cost_in_invoice = true` is set in `halyard.toml`.

`--dry-run` previews the invoice without writing or incrementing the counter.

## What this change does NOT do

- No multi-turn conversation for `halyard log`. Single-turn tool use only for
  v0.1. A persistent session REPL is a future scope item.
- No automatic time entry approval. The user controls open/close manually with
  `halyard start / stop`.
- No e-filing or PDF transmission. The invoice file is the output; sending it
  is the user's responsibility.
- No AI-assisted time entry review (reviewing timeclock for gaps). That is a
  separate v0.2 scope item.

## Key decisions

**Why structured output, not a free-form chat REPL?**

Antigravity (Gemini CLI) identified this as the most important architectural
choice in the wave. A structured `LogQueryResponse` makes the command:
- Testable: pytest can assert on typed fields, not string matching
- Composable: `halyard log --json | jq '.cost_usd'` works reliably
- Extensible: adding a new field to the response type is a backward-compatible
  change; adding a new sentence to free-form text is not

**Why single-turn?**

The queries users have are retrieval queries — "what did I spend on Acme this
month" — not iterative reasoning tasks. Single-turn with tool use handles all
plausible v0.1 queries. A multi-turn REPL adds complexity (session state,
context window management) that is not justified by the use cases we have.

**Why Jinja2 for invoice templates?**

Jinja2 is already in the stack and in `pyproject.toml`. Users who want to
customize their invoice format already have a well-documented template language.
Adding a second templating system would be unnecessary complexity.

**Why typst for PDF, not Pandoc or wkhtmltopdf?**

typst produces high-quality PDFs from markdown-like source with no LaTeX
dependency. It is already in the stack spec (see `openspec/project.md`).
The PDF step is optional — users who don't have typst installed get the
markdown output and a clear error message explaining how to add PDF support.

## Success criteria

- `halyard log "what did I spend on AI this month"` returns a structured,
  readable answer derived from real log data, in under 5 seconds.
- `halyard log --json "summarize by project"` emits valid JSON with `cost_usd`,
  `input_tokens`, `output_tokens`, and `project` fields per project.
- `halyard invoice acme --project auth-migration --period 2026-04` produces a
  complete invoice markdown at the correct path. The counter increments.
- `halyard invoice ... --dry-run` shows a preview without writing.
- Both commands have pytest coverage at the unit level. `halyard invoice` has a
  golden-file render test. `halyard log` has a mock-SDK test verifying tool
  dispatch and response parsing.
