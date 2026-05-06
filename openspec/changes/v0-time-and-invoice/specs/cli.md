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
- AND generates `invoices/2026-04-acme-001.md` and the corresponding `.pdf`
- AND increments the invoice counter in `halyard.toml`
- AND opens the PDF using the platform-default viewer

### Scenario: no time logged

- WHEN there are zero entries in the requested range for the requested client
- THEN the CLI exits with code 1 and a clear message
- AND no files are written

### Scenario: explicit date range

- WHEN the user runs `halyard invoice acme --from 2026-04-01 --to 2026-04-15`
- THEN the same logic as `--month` applies, scoped to that range

## Requirement: halyard (bare command, REPL mode)

The CLI MUST drop into an interactive Claude session when invoked with no
subcommand.

### Scenario: conversational logging

- WHEN the user runs `halyard`
- AND types "I just finished 2 hours on Globex"
- THEN the agent proposes the timeclock entry, the user confirms,
  the file is appended, and the agent waits for the next message

### Scenario: query

- WHEN the user types "how many hours have I billed ACME this quarter"
- THEN the agent runs the equivalent `hledger -f time.timeclock` query
- AND returns a table or short prose summary
- AND no files are modified

### Scenario: graceful exit

- WHEN the user types `/quit` or sends EOF (Ctrl-D)
- THEN the REPL exits cleanly with code 0
