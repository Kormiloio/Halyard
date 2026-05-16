# v2.50 — Halyard MCP Server: Design

## Module: `src/halyard/mcp_server.py`

`build_server() -> FastMCP` (lazy `from mcp.server.fastmcp import
FastMCP` inside the function so importing `halyard` never needs the
SDK). Pure data helpers live at module top (no MCP import) so they are
unit-testable without the SDK installed:

- `_aggregate_sessions() -> list[AiSession]` — dedup union via
  `reports.aggregate_session_dirs()` + `parse_sessions` +
  `reports._dedup_sessions` (the v2.48 layer).
- `_period_window(period)` → `(start, end, label)` for
  `"7d"|"30d"|"month"|"all"`.
- `_work_summary(period)`, `_sessions(...)`, `_spend(...)`,
  `_project_breakdown(period)`, `_cost_by_model(period)`,
  `_outcomes_status(period)` — return plain JSON-able dicts/lists.

`build_server()` wraps each helper as a FastMCP `@mcp.tool()` with
typed args + docstrings (the docstrings are the agent-facing tool
descriptions; write them for an LLM caller). All tools are read-only.

### Tool surface

| tool | args | returns |
|---|---|---|
| `work_summary` | `period="30d"` | period label, sessions, total_cost, by_tool, top_projects, adrift count+pct, outcomes, generated_at |
| `sessions` | `limit=20, project=None, tool=None, since=None` | list of {start,end,tool,model,input,output,cost,project,branch} |
| `spend_in_range` | `start, end, api_only=True, project=None` | {usd, sessions, period} via `usage.sum_spend` |
| `project_breakdown` | `period="30d"` | per-project {sessions, cost} sorted desc |
| `cost_by_model` | `period="30d"` | per-model {sessions, tokens, cost} |
| `outcomes_status` | `period="30d"` | {merged, open, closed, none, not_synced} |

Cost figures route through `usage.round_money` for consistency with
the rest of the app.

## CLI: `src/halyard/cli_mcp.py`

`register(app)` adds `halyard mcp` (visible command). Body:

```
try: from halyard.mcp_server import build_server
except ModuleNotFoundError:
    console.print("MCP SDK not installed — `pip install 'halyard[mcp]'`"); raise Exit(1)
build_server().run()        # FastMCP default = stdio transport
```

Wired in `cli.py` next to the other `register(app)` calls.

## Packaging

`pyproject.toml` `[project.optional-dependencies]`:
`mcp = ["mcp>=1.2"]` and add `mcp` to the `all` extra. Core deps
unchanged.

Repo-root `.mcp.json` (and a README/docs snippet):
```
{ "mcpServers": { "halyard": { "command": "halyard", "args": ["mcp"] } } }
```
so a user adds Halyard to Claude Code/Cursor in one step.

## Tests (`tests/test_v250_mcp_server.py`)

SDK-free: import `halyard.mcp_server`, monkeypatch
`aggregate_session_dirs` to two tmp project logs, then assert each
`_*` helper returns correct shapes/values (work_summary totals,
sessions filter, spend window, project/model breakdown, outcomes).
Also assert `halyard mcp` without the SDK exits 1 with the actionable
message (monkeypatch the import to raise). The MCP/stdio protocol
itself is the SDK's responsibility — not retested here.

Full `pytest`+`ruff`+`ruff format --check`+`mypy` before commit.
mypy: guard the optional import (`# type: ignore` / `TYPE_CHECKING`)
so the missing SDK doesn't fail type-check.
