# v2.50 — Halyard MCP Server

## Problem

Halyard's thesis is "AI Work Intelligence," yet the ledger is only
reachable through human surfaces (CLI, web, TUI). The agent that
*generates* the work can't ask about it. claude-mem's leverage comes
from exposing its data via MCP so the agent queries it in-context;
Halyard has no equivalent.

## Goal

A **read-only** MCP server, `halyard mcp` (stdio), that lets Claude
Code / Cursor / any MCP client query the local ledger directly:

- `work_summary` — one-call rollup (the flagship): period totals,
  cost, sessions, by-tool, top projects, adrift %, outcomes.
- `sessions` — recent sessions (filterable by project/tool/since).
- `spend_in_range` — cost for a window (reuses `usage.sum_spend`).
- `project_breakdown` — sessions + cost per project.
- `cost_by_model` — cost/tokens per model.
- `outcomes_status` — merged/open/closed/none/not-synced counts.

Mirrors claude-mem's layered API (precise tools + a smart rollup).
Ships a `.mcp.json` so registration is one step.

## Constraints honored

- **Read-only.** No tool mutates anything (upholds "no silent
  writes"). It only reads the existing plain-text ledger.
- **No new runtime / no daemon.** In-process Python, reusing the v2.48
  aggregate data layer (`aggregate_session_dirs`,
  `build_ai_report(sessions=…)`, `usage.sum_spend`, `parse_sessions`).
  stdio transport = the MCP client spawns it per session; nothing
  long-lived (the daemon anti-pattern we rejected).
- **Privacy.** Surfaces only metadata already in the ledger — no
  prompts, no code, no transcripts.
- **Lean core.** `mcp` SDK is an *optional* dependency
  (`pip install 'halyard[mcp]'`); the command lazy-imports and prints
  an actionable message if absent. Core install unchanged.

## Non-goals

- Write/mutation tools, auth, or remote exposure (stdio local only).
- Aggregating per-project panels beyond what v2.48 already does.
- Vector/semantic search (Halyard is a metrics ledger, not memory).

## Out of scope

Packaging Halyard as a full Claude Code plugin (skills/ui) — later,
after the OSS launch checklist.
