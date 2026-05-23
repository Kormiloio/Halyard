# Spec — Halyard MCP server

## Requirement: Read-only MCP server command

WHEN `halyard mcp` runs AND the `mcp` SDK is installed
THEN it MUST start an MCP server over stdio exposing the documented
read-only tools.
WHEN the `mcp` SDK is not installed
THEN it MUST exit non-zero with an actionable message naming
`pip install 'halyard[mcp]'`, and MUST NOT traceback.

## Requirement: No mutation, no network, no daemon

The server MUST NOT expose any tool that writes, deletes, or mutates
ledger/config/state. Transport MUST be stdio (no listening socket).
No long-lived background process is created.

## Requirement: Data from the aggregate ledger

Every tool MUST source sessions from the deduplicated union of all
registered project logs + hub (the v2.48 aggregate layer), never a
single hard-coded directory. Monetary values MUST use the shared
`usage` rounding.

## Requirement: Privacy

Tools MUST return only metadata already present in the ledger
(timestamps, tool, model, tokens, cost, project, branch, outcome).
They MUST NOT return prompts, code, transcripts, or file contents.

## Requirement: Tool surface

The server MUST expose at least: `work_summary` (period rollup),
`sessions`, `spend_in_range`, `project_breakdown`, `cost_by_model`,
`outcomes_status`. `work_summary` MUST answer in a single call
(totals, cost, by-tool, top projects, adrift, outcomes).

## Requirement: Optional dependency, lean core

The `mcp` SDK MUST be an optional extra; importing `halyard` or running
any non-`mcp` command MUST NOT require it.

## Requirement: One-step registration

The repo MUST ship a `.mcp.json` registering the server as
`{"command":"halyard","args":["mcp"]}` and document it.
