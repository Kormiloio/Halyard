# CLI Spec

## Requirement: halyard init

The CLI MUST scaffold a new Halyard project in the current directory.

### Scenario: first-time setup

- WHEN the user runs `halyard init` in an empty directory
- THEN the CLI creates `halyard.toml`, `clients.toml`, `projects.toml`,
  `time.timeclock`, `invoices/`, and `.gitignore`
- AND prints a welcome message with three suggested next commands

### Scenario: existing Halyard project

- WHEN the user runs `halyard init` in a directory containing `halyard.toml`
- THEN the CLI exits with code 1
- AND prints a message instructing the user to remove or move the existing
  project before re-initializing

## Requirement: halyard log (natural language)

The CLI MUST accept a free-form string and use Claude to extract a
timeclock entry.

### Scenario: simple past-tense log

- WHEN the user runs `halyard log "worked 3h on ACME auth migration this morning"`
- THEN Claude extracts client=acme, project=auth-migration, duration=3h,
  start=this morning (resolved against the current local date)
- AND the CLI displays the proposed timeclock lines and prompts for confirmation
- AND on confirmation, appends them to `time.timeclock`

### Scenario: ambiguous client

- WHEN the user logs time against a client name not present in `clients.toml`
- THEN Claude proposes adding the client
- AND asks for the hourly rate before logging the time entry

### Scenario: declined confirmation

- WHEN the user is prompted to confirm a proposed entry and declines
- THEN no files are written
- AND the CLI exits cleanly with code 0

## Requirement: halyard start / stop

The CLI MUST support live timing.

### Scenario: start a timer

- WHEN the user runs `halyard start acme/auth-migration`
- THEN the CLI writes an `i` line to `time.timeclock` with the current
  timestamp and the slug `acme:auth-migration`
- AND records the active timer in `~/.halyard/active`

### Scenario: stop the active timer

- WHEN the user runs `halyard stop` and a timer is active
- THEN the CLI writes an `o` line to `time.timeclock` with the current timestamp
- AND clears the active timer file

### Scenario: stop with no active timer

- WHEN the user runs `halyard stop` and no timer is active
- THEN the CLI exits with code 1 and a clear message

## Requirement: halyard invoice

The CLI MUST generate invoices from time entries for a client and date range.

### Scenario: invoice last month for a client

- WHEN the user runs `halyard invoice acme --month last`
- THEN the CLI reads `time.timeclock`, sums hours by project for ACME in
  the prior calendar month
- AND applies hourly rates from `clients.toml` (with project-level overrides
  from `projects.toml` taking precedence)
- AND generates `invoices/2026-04-001-acme.md`
- AND increments the invoice counter in `halyard.toml`

### Scenario: PDF generation and auto-open

- WHEN the user runs `halyard invoice acme --period 2026-05 --pdf`
- THEN the CLI generates the markdown invoice
- AND calls `typst compile` to produce the corresponding `.pdf`
- AND opens the PDF using the platform-default viewer (`open` on macOS,
  `xdg-open` on Linux, `os.startfile` on Windows)
- IF `typst` is not installed THEN the CLI prints a warning and exits 0
  without failing the invoice write

### Scenario: no time logged

- WHEN there are zero closed entries in the requested range for the requested client
- THEN the CLI exits with code 1 and a clear message
- AND no files are written

### Scenario: unknown client

- WHEN the client slug does not appear in `clients.toml`
- THEN the CLI exits with code 1 with message "Client 'X' not found in clients.toml"

### Scenario: open (unclosed) time entries

- WHEN there are open (clock-in without clock-out) entries for the client in the period
- THEN the invoice is still generated from closed entries
- AND the CLI prints a warning listing the open entry start times

### Scenario: invoice already exists

- WHEN an invoice file already exists for the period and client
- AND `--force` is not passed
- THEN the CLI exits with code 1 with message "Invoice already exists: ... Use --force to overwrite"

### Scenario: explicit date range

- WHEN the user runs `halyard invoice acme --from 2026-04-01 --to 2026-04-15`
- THEN the same logic as `--month` applies, scoped to that range

## Requirement: halyard (bare command, REPL mode)

The CLI MUST drop into an interactive natural-language query loop when invoked
with no subcommand. The REPL answers questions about captured AI work metadata
— sessions, cost, models, projects — using the local log agent by default.

### Scenario: query about AI spend

- WHEN the user runs `halyard` inside a Halyard project directory
- AND types "how much did I spend on Claude Code this month?"
- THEN the REPL routes the query to `run_log_query()` with agent=local
- AND prints the answer followed by per-project and per-model breakdowns
  where relevant
- AND waits for the next message

### Scenario: no project found

- WHEN the user runs `halyard` outside any Halyard project directory
  and no hub is configured
- THEN the CLI exits with code 1 and prints "No Halyard project found.
  Run halyard init to create one."

### Scenario: provider switching

- WHEN the user types `/agent claude` in the REPL
- THEN subsequent queries use the Claude agent (requires ANTHROPIC_API_KEY)
- WHEN the user types `/agent local`
- THEN the REPL reverts to the local agent

### Scenario: time window

- WHEN the user types `/period today`
- THEN subsequent queries are scoped to the current calendar day

### Scenario: graceful exit

- WHEN the user types `/quit` or `/q` or sends EOF (Ctrl-D)
- THEN the REPL exits cleanly with code 0
- AND readline history is persisted to `~/.halyard/repl_history`

### Slash commands

| Command | Behavior |
|---------|----------|
| `/agent local\|claude\|openai` | Switch query provider |
| `/model <name>` | Set model for cloud providers |
| `/period today\|week\|month\|all` | Change time window |
| `/help` or `/?` | Print help |
| `/quit` or `/q` or Ctrl-D | Exit |
