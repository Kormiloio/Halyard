# PRD: Developer Experience Wave

**Status:** In progress  
**Covers:** v0.1 (log + invoice), v0.2/v0.3 (`halyard log` agents),
v2.4 (data integrity), v4 (TUI)  
**Last meaningful update:** May 2026

---

## Background

Halyard's collection layer is solid. v0 through v2.3 shipped a working stack:
hooks for Claude Code, Cursor, and Gemini CLI; dynamic pricing; budget alerts;
a local dashboard; and a Beancount ledger. The `ai-sessions.log` protocol is
proven in daily use.

Three AI tools — Claude CLI, Cursor, and Antigravity (Gemini CLI) — were asked
independently to evaluate the project and recommend improvements. Their
feedback converged on the same four gaps:

1. **v0 stubs block real-world use.** `halyard log` and `halyard invoice` both
   raise `NotImplementedError`. They are the two most user-visible commands in
   the product, and neither works. Every other capability is being captured into
   a log that can't be read by an agent or invoiced.

2. **Silent drops erode trust.** When a session can't be attributed to a project
   (no active timer, no matching git remote, hub not configured) the collector
   silently emits a record with `project=""` — or the hook exits 0 and the
   session is lost. Users have no way to know what they're missing. This
   violates the non-negotiable: *No silent writes.*

3. **Data contracts are missing.** `AiSession` is parsed from raw log lines at
   read time with no validation. A malformed line is silently skipped. A field
   added in v2.3 that an older tool writes as `None` gets dropped. The schema is
   implicit and fragile — this will become a maintenance problem as the log
   format evolves.

4. **`halyard log` is the wrong shape.** The command is a REPL stub. The right
   shape is a structured Claude SDK call that: reads the log, runs tool use
   against the local files, and returns a typed response. This is Antigravity's
   best observation and the most technically interesting item in the wave.

This PRD covers the changes that address these four gaps, plus the directional
decision on a Textual TUI that was surfaced by Antigravity and endorsed by the
team.

---

## Change 1: Close v0 — `halyard log` and `halyard invoice`

### Implementation status — May 7, 2026

Agent-backed log slice implemented.

- `halyard invoice` now generates markdown invoices from local
  `time.timeclock`, `clients.toml`, `projects.toml`, and `halyard.toml`; it
  supports `--period`, `--project`, `--dry-run`, `--pdf`, `--force`, and
  `--rate`.
- `halyard log` now returns a deterministic local metadata summary with
  `--json`, `--agent local`, and simple named periods (`today`, `week`,
  `month`, `all`). The query layer is provider-neutral: model-backed agents are
  reasoning providers over the same local data, not filters on which AI tools
  can be queried.
- The local provider now recognizes simple query intent for tool names
  (`cursor`, `claude`, `gemini`, `codex`), periods, project slugs, model
  substrings, and branch tags. Explicit flags (`--tool`, `--project`,
  `--model-filter`, `--branch`) override inferred intent.
- `--agent claude` runs the Anthropic SDK tool-use loop against local Halyard
  metadata and requires `ANTHROPIC_API_KEY`.
- `--agent openai` runs an OpenAI-compatible tool-use loop against OpenAI,
  Ollama, LM Studio, vLLM, or similar endpoints. `OPENAI_API_KEY` is required
  only for the hosted OpenAI API; local endpoints can be selected with
  `--base-url`.
- `~/.halyard/config.toml` can set personal defaults for `log.default_agent`,
  `log.openai_base_url`, `log.openai_model`, and `log.claude_model`; CLI flags
  override config values.

Still pending: broader structured-output hardening and richer tool coverage
against ledger/budget data. The current agent loop answers through a typed
`LogQueryResponse` wrapper and captures structured summaries from tool calls,
but final model text is still provider-native prose.

### The gap

`halyard log` is the primary way a user is supposed to interact with their
captured data through natural language. It was always intended as an AI agent
loop that reads `ai-sessions.log`, `time.timeclock`, and the ledger files, and
answers questions. Today it is a `raise NotImplementedError`.

`halyard invoice` is the output stage of the v0 time-and-invoice loop: read the
timeclock, pull project/client metadata, render an invoice markdown file, and
optionally generate a PDF. Also a stub.

### What we're building

**`halyard log`** — An AI agent command backed by local, Anthropic, or
OpenAI-compatible providers:

- Single-turn tool use loop. The model receives system context (project config,
  pricing table, budget state) and the contents of `ai-sessions.log`.
- Structured rendering through `LogQueryResponse`. Tool-derived summaries are
  normalized for tables and `--json`; final answer prose still comes from the
  selected provider.
- Tools available to the agent: `read_sessions`, `read_timeclock`,
  `read_ledger`, `summarize_by_project`, `summarize_by_model`, `cost_by_branch`.
- Natural language queries: "What did I spend on the Acme project this month?"
  "Which model is costing me the most?" "Show me yesterday's sessions."
- No prompt content capture. The agent only has access to metadata log files,
  not the content of any AI conversation.

**`halyard invoice`** — Reads `time.timeclock`, `clients.toml`, `projects.toml`,
and `halyard.toml` to generate a Jinja2-rendered invoice markdown file:

- Detects open time entries and warns before generating.
- Increments `invoice_counter` in `halyard.toml` atomically.
- Writes to `invoices/YYYY-MM-{counter}-{client}.md`.
- Optional `--pdf` flag calls typst (subprocess) to render PDF alongside the
  markdown. Degrades gracefully if typst is not installed.
- Optionally includes AI session cost breakdown as a line item (opt-in via
  `halyard.toml: include_ai_cost_in_invoice = true`).

### Success criteria

- `halyard log "what did I spend on AI this month"` returns a structured,
  readable answer derived from real log data.
- `halyard invoice acme` produces a complete, correctly dated invoice markdown
  file. The counter increments. Re-running the same command with `--dry-run`
  shows a preview without writing.
- Both commands are covered by pytest (golden-file tests for invoice render;
  mock-SDK tests for log agents).

---

## Change 2: Data integrity — no-silent-writes and schema validation

### Implementation status — May 7, 2026

First slice implemented.

- Collectors preserve sessions that would previously have been dropped by
  writing them to `~/.halyard/unattributed.log` and warning on stderr.
- `AiSession.from_log_line()` validates required fields, token/cost types, and
  non-negative numeric values; malformed lines are quarantined in
  `~/.halyard/quarantine.log`.
- `halyard check-log` validates `ai-sessions.log`.
- `halyard report` now warns when the global unattributed log has recoverable
  sessions.
- `halyard assign-unattributed` now reviews `~/.halyard/unattributed.log` and
  lets the user assign sessions to the current project, move them to the hub,
  discard them, or skip them.

Still pending: a design document for the final serialization/quarantine shape
and any broader migration guidance for older logs.

### The gap

Two related problems that compound each other:

**Silent drops.** The Gemini CLI and Cursor collectors call `find_project_dir()`
and fall back to the hub. If neither is found, `handle_agent_stop()` calls
`_reset_state()` and returns 0 — silently discarding the session. The user
never knows. The same happens in Claude Code: if the project dir has no
`ai-sessions.log` the session is dropped.

**Schema drift.** `AiSession` fields are written as space-separated key=value
pairs on a single log line. When a new field is added (e.g., `job_id`, `note`),
older readers silently skip it. When a value is `None`, different collectors
write it differently (empty string vs. absent key). There is no canonical
round-trip test. This is manageable now but will cause subtle bugs as the field
count grows.

### What we're building

**No-silent-writes for collectors:**

- When a session cannot be attributed to any project (no `project_dir`, no
  hub), the collector writes the session to `~/.halyard/unattributed.log`
  instead of dropping it.
- A warning is printed to stderr: `[halyard] session written to unattributed
  log — run 'halyard assign-unattributed' to review.`
- `halyard assign-unattributed` is a new command that reads the unattributed
  log, presents each session, and lets the user assign or discard it.
- Existing `halyard report` includes an unattributed line in the summary if
  the file is non-empty.

**AiSession schema validation:**

- `AiSession` gets an explicit `from_log_line(line: str) -> AiSession | None`
  class method with field-level validation: types, required fields, sane ranges.
  Malformed lines write to a quarantine log (`~/.halyard/quarantine.log`) with
  the original line and parse error — never silently discarded.
- `AiSession.to_log_line() -> str` is the canonical serializer. All collectors
  use it. No ad-hoc string formatting.
- A `halyard check-log` command validates an `ai-sessions.log` file and reports
  any quarantine-worthy lines with the error.
- Round-trip property test: `from_log_line(s.to_log_line()) == s` for all valid
  sessions.

### Success criteria

- Killing a collector in a directory with no `halyard.toml` and no hub writes to
  `~/.halyard/unattributed.log` and prints a warning — never silently exits.
- `halyard check-log` on a valid log exits 0 with "All N lines valid."
- `halyard check-log` on a log with a malformed line exits 1, names the line,
  and reports the field-level error.
- All existing collectors use `AiSession.to_log_line()` — no ad-hoc formatting.

---

## Change 3: TUI — Textual interactive terminal dashboard

### Implementation status — May 7, 2026

First vertical slice implemented.

- v4 proposal, design, spec, and task checklist are written with the five design
  decisions locked.
- `halyard tui` launches a Textual application when installed with
  `halyard[tui]`; the base install remains lean and prints a clear install
  instruction when Textual is missing.
- The first layout renders a session feed, budget status panel, model breakdown
  panel, header/status line, and footer key hints.
- `SessionStore` loads `ai-sessions.log`, tails appended lines with
  `watchfiles`, and filters by time window, project scope, and branch tag.
- Keyboard shortcuts for `d`/`w`/`m`/`a` time windows, `p` project scope, and
  `b` branch filter, and `q` quit are wired.
- The branch filter modal lists branch tags by recency; Enter applies a branch
  filter and Escape clears it.

Still pending: project drill-down, help panel, new-row highlighting, richer
budget/project detail views, and explicit log rotation re-open behavior.

### The gap

The current `halyard dashboard` is a Rich auto-refreshing table. It works and
it's readable. But it's static: you can't drill down, filter by project, change
the time window, or navigate between views without re-running the command with
different flags. It is a one-way display, not an instrument.

Antigravity (Gemini CLI) surfaced this as the most significant UX gap after data
integrity. Cursor's feedback about "daily driver" UX pointed at the same thing:
a tool that surfaces the right data in context without requiring the user to
compose the right flags.

### What a TUI would do

The TUI is a [Textual](https://textual.textualize.io/) application that replaces
the static Rich dashboard with an interactive terminal UI:

- **Live session feed** — new sessions appear as they're appended to the log,
  with color-coded tool icons and cost.
- **Project drill-down** — cursor keys navigate into a project to see its
  session history, model mix, and daily spend chart.
- **Branch view** — filter sessions by `branch:` tag to see per-branch cost.
- **Budget status panel** — shows current daily/monthly spend vs limits for all
  projects, color-coded by proximity to limit.
- **Model breakdown** — a sparkline or bar chart showing token/cost distribution
  across models used in the current period.
- **Time window** — configurable to today / this week / this month / all time,
  switchable with keyboard shortcuts.

### Design decisions

The v4 OpenSpec locks the TUI as a supplement to `halyard dashboard`, ships
Textual/watchfiles as the optional `halyard[tui]` extra, keeps session state in
memory with a file watcher, stays read-only for v4, and prefers the hub log
when configured.

---

## Sequencing

| Priority | Change | Rationale |
|----------|--------|-----------|
| 1 | v0.1 — Close v0 | Blocks real-world daily use. `halyard log` is the product pitch. |
| 2 | v2.4 — Data integrity | Low implementation cost, high trust payoff. Prevents data loss. |
| 3 | v4 — TUI design decisions | Define the five open questions; write specs. Implementation follows. |

---

## What this wave does NOT include

- **Unix socket daemon.** Antigravity proposed a persistent background process
  for faster hook response times. Rejected for now: adds operational complexity
  (process management, PID files, crash recovery) that is not justified by the
  current hook latency. Revisit if hook startup time becomes a real user
  complaint.

- **Redaction.** Antigravity proposed automatic PII scrubbing from session
  notes and tags. Not in scope for this wave: Halyard currently captures no
  prompt or code content. Session metadata (model names, token counts, project
  slugs) is not PII. If sensitive content capture is ever added as an opt-in
  feature, redaction becomes a first-class spec at that point.

- **Reconciliation.** Cursor suggested a deduplication pass that detects
  near-duplicate sessions (same time window, same tool, same project). Deferred:
  the current dedup mechanism (`job_id=` tag) handles the primary case. Fuzzy
  dedup needs a false-positive analysis before committing to the approach.

- **`halyard report --branch`.** The data exists (all sessions carry
  `branch:<name>` tags). The command does not. Punted to a v2.x follow-up since
  it is additive reporting, not a data integrity fix.
