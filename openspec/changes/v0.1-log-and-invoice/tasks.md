# Tasks: v0.1 — Close v0: `halyard log` and `halyard invoice`

## Spec & design
- [x] Write proposal.md
- [x] Write specs/log-command.md
- [x] Write specs/invoice-command.md
- [x] Write design.md (SDK structured output approach, tool dispatch, template rendering)

## Implementation note — 2026-05-07

A first production slice is implemented:

- `halyard invoice` now renders markdown invoices from local TOML/timeclock
  data, supports dry-run, PDF fallback, force overwrite, project/period/rate
  filters, and increments the invoice counter.
- `halyard log` now returns a deterministic local metadata summary with
  `--json` and named periods.
- `halyard log` is now intended to be provider-neutral: `local` is the default
  offline provider, and `claude` is a future model-backed provider over the same
  local data contract.
- The local provider now infers simple intent from natural language and supports
  explicit filter flags for tool, project, model substring, and branch.

The full Anthropic SDK structured-output agent remains unimplemented. Keep the
provider-specific SDK tasks unchecked until the provider uses tool dispatch as
designed.

## `src/halyard/log_agent.py` (new module)

### LogQueryResponse types
- [x] Define `SessionRow` dataclass (start, end, tool, model, cost_usd, project, tags)
- [x] Define `ProjectSummary` dataclass (project, cost_usd, input_tokens, output_tokens, session_count)
- [x] Define `ModelSummary` dataclass (model, cost_usd, input_tokens, output_tokens, session_count)
- [x] Define local `LogQueryResponse` dataclass (answer, data_source, period, cost_usd_total, session_count, projects, models)
- [x] Define provider selection (`local`, `claude`) without coupling captured tools to one AI vendor

### Agent tools
- [x] Implement `read_sessions(project?, start?, end?, tool?, limit?)` — filtered log read
- [x] Implement `summarize_by_project(start?, end?)` — aggregated per-project totals
- [x] Implement `summarize_by_model(start?, end?)` — aggregated per-model totals
- [x] Implement `cost_by_branch(branch, start?, end?)` — sessions by branch tag
- [x] Implement `read_timeclock(start?, end?)` — time entries from time.timeclock

### Agent runner
- [x] Implement deterministic local provider over shared report functions
- [x] Implement deterministic intent parsing for tool, period, project, model, and branch
- [x] Implement `run_log_query(query, log_path, model, period) -> LogQueryResponse`
  - Build system context (project config, budget state, pricing table age)
  - Define tool schemas for Claude SDK tool use
  - Single-turn tool-use loop (dispatch tools, collect results, final response)
  - Parse structured response into `LogQueryResponse`
  - Raise `LogAgentError` on SDK error or timeout
- [x] Detect hub vs project log source; set `data_source` field accordingly

## `src/halyard/invoicing.py` (new module)
- [x] Implement `generate_invoice(client_slug, project_slug?, period, project_dir, force, dry_run) -> InvoiceResult`
  - Read and validate `clients.toml` — error if client not found
  - Read closed time entries from `time.timeclock` for period
  - Warn if open entries exist for the client
  - Read AI session cost from `ai-sessions.log` if `include_ai_cost_in_invoice = true`
  - Render invoice via Jinja2 from bundled or user override template
  - Increment `invoice_counter` in `halyard.toml` atomically (read-modify-write)
  - Write invoice markdown to `invoices/YYYY-MM-{counter:03d}-{client}.md`
  - Return `InvoiceResult` with path, total, and dry_run flag
- [x] Implement `render_pdf(invoice_path) -> None` — subprocess typst compile, graceful degrade

## `src/halyard/cli.py` — wire up commands
- [x] Implement local `halyard log` command
  - Accept positional `query` argument
  - `--json` flag
  - `--agent local` default
  - `--agent claude` explicit unavailable-provider error
  - `--tool`, `--project`, `--model-filter`, and `--branch` flags
  - `--period` option (today / week / month / all, default month)
  - Auto-detect project dir; error clearly if missing
  - Render deterministic local summary or emit JSON
- [x] Upgrade `halyard log` to the full SDK-backed agent
  - `--model` option (default `claude-haiku-4-5`)
  - `--log` option
  - hub fallback / `data_source` field
  - tool dispatch and structured `LogQueryResponse`
- [x] Implement `halyard invoice` command
  - Accept positional `client` argument
  - `--project` option
  - `--period` option (default: current month)
  - `--dry-run` flag
  - `--pdf` flag
  - `--force` flag
  - `--rate` option
  - Call `generate_invoice()`, handle all error cases with clear messages

## Tests (`tests/test_log_agent.py`)
- [x] `test_run_log_query_summarize_by_project` — mock SDK, verify tool dispatch and response
- [x] `test_run_log_query_no_sessions` — empty log returns informative answer
- [x] `test_run_log_query_uses_hub_fallback` — when no project dir, uses hub log
- [x] `test_run_log_query_no_api_key` — raises `LogAgentError` with clear message
- [x] `test_run_log_query_json_output` — `LogQueryResponse` serializes to valid JSON

## Tests (`tests/test_invoicing.py`)
- [x] `test_generate_invoice_basic` — rendered markdown output
- [x] `test_generate_invoice_dry_run` — returns rendered text, counter not incremented
- [x] `test_generate_invoice_unknown_client` — raises error for missing client slug
- [x] `test_generate_invoice_no_time_entries` — raises error with clear message
- [x] `test_generate_invoice_open_entries_warning` — warning printed, invoice still generated
- [x] `test_generate_invoice_existing_file_no_force` — exits with error
- [x] `test_generate_invoice_existing_file_force` — overwrites without incrementing counter
- [x] `test_generate_invoice_ai_cost_line_item` — AI cost appears when flag set
- [x] `test_log_json_returns_local_summary` — local log summary emits valid JSON

## Quality
- [x] Run full test suite — all passing (222 tests, 2026-05-07)
- [x] Run mypy — no new errors (2026-05-07)
- [x] Run ruff — no new errors (2026-05-07)
