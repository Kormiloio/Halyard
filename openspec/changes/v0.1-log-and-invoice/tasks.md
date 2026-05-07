# Tasks: v0.1 — Close v0: `halyard log` and `halyard invoice`

## Spec & design
- [ ] Write proposal.md
- [ ] Write specs/log-command.md
- [ ] Write specs/invoice-command.md
- [ ] Write design.md (SDK structured output approach, tool dispatch, template rendering)

## `src/halyard/log_agent.py` (new module)

### LogQueryResponse types
- [ ] Define `SessionRow` dataclass (start, end, tool, model, cost_usd, project, tags)
- [ ] Define `ProjectSummary` dataclass (project, cost_usd, input_tokens, output_tokens, session_count)
- [ ] Define `ModelSummary` dataclass (model, cost_usd, input_tokens, output_tokens, session_count)
- [ ] Define `LogQueryResponse` dataclass (answer, data_source, period, cost_usd_total, session_count, projects, models, sessions)

### Agent tools
- [ ] Implement `read_sessions(project?, start?, end?, tool?, limit?)` — filtered log read
- [ ] Implement `summarize_by_project(start?, end?)` — aggregated per-project totals
- [ ] Implement `summarize_by_model(start?, end?)` — aggregated per-model totals
- [ ] Implement `cost_by_branch(branch, start?, end?)` — sessions by branch tag
- [ ] Implement `read_timeclock(start?, end?)` — time entries from time.timeclock

### Agent runner
- [ ] Implement `run_log_query(query, log_path, model, period) -> LogQueryResponse`
  - Build system context (project config, budget state, pricing table age)
  - Define tool schemas for Claude SDK tool use
  - Single-turn tool-use loop (dispatch tools, collect results, final response)
  - Parse structured response into `LogQueryResponse`
  - Raise `LogAgentError` on SDK error or timeout
- [ ] Detect hub vs project log source; set `data_source` field accordingly

## `src/halyard/invoicing.py` (new module)
- [ ] Implement `generate_invoice(client_slug, project_slug?, period, project_dir, force, dry_run) -> InvoiceResult`
  - Read and validate `clients.toml` — error if client not found
  - Read closed time entries from `time.timeclock` for period
  - Warn if open entries exist for the client
  - Read AI session cost from `ai-sessions.log` if `include_ai_cost_in_invoice = true`
  - Render invoice via Jinja2 from bundled or user override template
  - Increment `invoice_counter` in `halyard.toml` atomically (read-modify-write)
  - Write invoice markdown to `invoices/YYYY-MM-{counter:03d}-{client}.md`
  - Return `InvoiceResult` with path, total, and dry_run flag
- [ ] Implement `render_pdf(invoice_path) -> None` — subprocess typst compile, graceful degrade

## `src/halyard/cli.py` — wire up commands
- [ ] Implement `halyard log` command
  - Accept positional `query` argument
  - `--json` flag
  - `--model` option (default `claude-haiku-4-5`)
  - `--log` option
  - `--period` option (today / week / month / all, default month)
  - Auto-detect project dir or hub; error clearly if neither found
  - Render `LogQueryResponse` as Rich panel or emit JSON
- [ ] Implement `halyard invoice` command
  - Accept positional `client` argument
  - `--project` option
  - `--period` option (default: current month)
  - `--dry-run` flag
  - `--pdf` flag
  - `--force` flag
  - `--rate` option
  - Call `generate_invoice()`, handle all error cases with clear messages

## Tests (`tests/test_log_agent.py`)
- [ ] `test_run_log_query_summarize_by_project` — mock SDK, verify tool dispatch and response
- [ ] `test_run_log_query_no_sessions` — empty log returns informative answer
- [ ] `test_run_log_query_uses_hub_fallback` — when no project dir, uses hub log
- [ ] `test_run_log_query_no_api_key` — raises `LogAgentError` with clear message
- [ ] `test_run_log_query_json_output` — `LogQueryResponse` serializes to valid JSON

## Tests (`tests/test_invoicing.py`)
- [ ] `test_generate_invoice_basic` — golden-file test for rendered markdown output
- [ ] `test_generate_invoice_dry_run` — returns rendered text, counter not incremented
- [ ] `test_generate_invoice_unknown_client` — raises error for missing client slug
- [ ] `test_generate_invoice_no_time_entries` — raises error with clear message
- [ ] `test_generate_invoice_open_entries_warning` — warning printed, invoice still generated
- [ ] `test_generate_invoice_existing_file_no_force` — exits with error
- [ ] `test_generate_invoice_existing_file_force` — overwrites without incrementing counter
- [ ] `test_generate_invoice_ai_cost_line_item` — AI cost appears when flag set

## Quality
- [ ] Run full test suite — all passing
- [ ] Run mypy — no new errors
- [ ] Run ruff — no new errors
