# v0.1 Design — `halyard log` and `halyard invoice`

## `halyard log` — provider-neutral query layer

### Module layout

```text
src/halyard/log_agent.py   — query dispatch, provider runners, local inference
src/halyard/log_config.py  — ~/.halyard/config.toml loader (agent, model, keys)
src/halyard/cli.py         — halyard log command wiring
```

### Data contract

`LogQueryResponse` (frozen dataclass) is the single output type across all
providers:

| Field | Type | Notes |
|---|---|---|
| `answer` | str | Human-readable answer text |
| `query` | str | Original query string |
| `agent` | `"local" \| "claude" \| "openai"` | Provider that answered |
| `data_source` | str | Path to log used; `"hub:<path>"` when hub fallback |
| `period` | str | Period used: today / week / month / all / dynamic |
| `cost_usd_total` | float | Total AI spend in matched sessions |
| `session_count` | int | Sessions matched |
| `human_minutes` | int | Human time in period (local only) |
| `filters` | `LogQueryFilters` | Active tool/project/model/branch filters |
| `projects` | `list[LogBucket]` | Per-project cost buckets |
| `models` | `list[LogBucket]` | Per-model cost buckets |

`LogQueryFilters` carries optional `tool`, `project`, `model`, and `branch`
values inferred from the query or passed explicitly via CLI flags.

### Provider dispatch

`run_log_query(query, *, project_dir, agent, ...)` is the public entry point.

1. If `project_dir` is `None`, fall back to `find_hub()`. Set
   `data_source = "hub:<path>"` to distinguish hub-sourced responses.
2. Resolve provider from `agent` arg or `~/.halyard/config.toml`.
3. Dispatch to the matching runner; use `dataclasses.replace` to rewrite
   `data_source` when the hub fallback was used.

```
run_log_query
  ├── run_local_log_query      — deterministic, no API key
  ├── run_claude_log_query     — Anthropic SDK tool-use loop (≤3 turns)
  └── run_openai_log_query     — OpenAI function-calling loop (≤3 turns)
```

### Local provider

`run_local_log_query` never calls an external API. It:

1. Runs intent inference (`_infer_period`, `_infer_tool`, `_infer_branch`,
   `_infer_filters`) to extract structured filters from the query string.
2. Calls shared report functions (`summarize_ai_sessions`, `parse_timeclock`)
   to build per-project and per-model buckets.
3. Constructs a templated `answer` string from the aggregates.

Intent inference uses substring matching, not ML. It is deterministic and has
no external dependencies.

### SDK providers (claude, openai)

Both SDK runners use a shared tool schema (`_TOOLS` / `_tools_for_openai`)
that exposes four read-only tools over local data:

| Tool | Returns |
|---|---|
| `read_sessions` | Filtered list of session rows |
| `summarize_by_project` | Per-project cost/count aggregates |
| `summarize_by_model` | Per-model cost/count aggregates |
| `read_timeclock` | Human time entries from time.timeclock |

All tool implementations call the same pure functions as the local provider.
The SDK loop runs at most 3 turns to prevent runaway token usage.

### Hub fallback

The CLI resolves `project_dir = find_project_dir() or find_hub()` before
calling `run_log_query`. Additionally, `run_log_query` itself accepts
`project_dir=None` and performs the same fallback internally, so library
callers that do not pre-resolve get consistent behavior.

---

## `halyard invoice` — local markdown invoice renderer

### Module layout

```text
src/halyard/invoicing.py   — generate_invoice(), render_pdf(), template logic
src/halyard/cli.py         — halyard invoice command wiring
```

### Data flow

```
clients.toml + time.timeclock + halyard.toml
    → generate_invoice()
        → line items (time × rate per project)
        → optional AI cost line item (from ai-sessions.log)
        → InvoiceView
        → Jinja2 template render
        → invoices/YYYY-MM-{counter:03d}-{client}.md
        → optional typst PDF compile
```

### Invoice counter

The counter lives in `halyard.toml` under `[invoicing] counter`. It is
incremented atomically (read → modify → write) after a successful write.
`--force` overwrites an existing file without incrementing.

### Error handling

| Condition | Behaviour |
|---|---|
| Client slug not in clients.toml | `InvoiceError` — named client not found |
| No closed time entries in period | `InvoiceError` — clear period + client message |
| Open time entries exist | Warning appended to `InvoiceResult.warning`; invoice still generated |
| Invoice file already exists | `InvoiceError` unless `--force` |

### AI cost line item

When `[invoicing] include_ai_cost_in_invoice = true` in `halyard.toml`, a
single "AI usage cost" line item is appended. The amount is the sum of
`cost_usd` for sessions whose project matches the billed accounts in the
billing period.

### PDF rendering

`render_pdf(invoice_path)` shells out to `typst compile`. If `typst` is not
on `PATH`, it logs a warning and returns without error. The markdown file is
always written first; PDF is an optional enhancement.
