# Tasks

Implementation checklist for v3.4 — MCP-server usage inventory.

## 0. Prerequisites

- [x] 0.1 v3.0–v3.2 complete.
- [x] 0.2 **Phase-0 spike** done 2026-05-18; findings in `design.md`.
  S1: Claude Code `tool_use` blocks carry `name` (wire it);
  Cursor/Gemini have no per-tool names → honest absence; Codex
  unconfirmed → deferred follow-up. S2: no `mcp__` collision anywhere.
  v3.4 = Claude-Code-only MCP usage (designed partial rollout).

## 1. Privacy primitive (shared, test-first)

- [x] 1.1 `MCP_SERVER_ALLOWLIST` frozenset + `reduce_mcp` in new
  `src/halyard/mcp_inventory.py` (dedicated module — keeps `leverage`
  focused): count always, allowlisted sorted CSV, None on empty.
- [x] 1.2 `extract_mcp_server` — exact `mcp__` prefix + first `__`
  delimiter anchor; None on non-match/malformed (no partial).
- [x] 1.3 Primitive unit-tested before collector wiring (9 tests:
  allowlist boundary, counted-not-named, garbled/empty → None).

## 2. Schema & log

- [x] 2.1 `db.py` migration appended **after** the v3.1 `(4,…)` as
  `(5,…)` (ascending order — caught/fixed an initial misorder); two
  additive `ALTER TABLE sessions` columns; `_CURRENT_VERSION` 5→6;
  `_CREATE_SCHEMA_V1` updated; idempotent self-heal verified.
- [x] 2.2 `AiSession.mcp_servers_used` / `mcp_server_names`;
  `to_log_line` + `_parse_line_result` round-trip; empty case
  byte-identical (v2.75 path intact).

## 3. Collector wiring

- [x] 3.1 Claude Code: existing `tool_use` loop now also reads `name`,
  reduces via `extract_mcp_server`, sets fields at close through
  `reduce_mcp`. v3.2 tool-call/error counts untouched (verified).
- [x] 3.2 Per Phase-0 S1: Cursor/Gemini have no per-tool names →
  honest absence (R5); Codex deferred. v3.4 = Claude-Code-only, the
  designed partial rollout. Honesty explicitly tested.

## 4. Surface (Leverage parity)

- [x] 4.1 Shared `summarize_mcp` + `render_mcp_phrase` + `McpRollup`
  in `leverage.py` (peak-session rollup — coherent data point).
- [x] 4.2 Web `_leverage_panel` (`.leverage-mcp` +CSS) + TUI
  `LeveragePane`; "+N" for counted-but-unnamed per R6; single shared
  phrase so they cannot diverge.
- [x] 4.3 Absent → no MCP line either surface; report & invoice
  untouched. Verified.

## 5. Tests (19, ≥15 required)

- [x] 5.1 primitive units (allowlist boundary, garbled, empty,
  counted-not-named).
- [x] 5.2 round-trip + byte-stable empty (v2.75 unaffected).
- [x] 5.3 additive migration v5→v6, idempotent, `_CURRENT_VERSION`==6.
- [x] 5.4 web↔TUI parity; absent → v3.2-identical; "+N" + "none on
  allowlist" rendering.
- [x] 5.5 partial-rollout honesty (non-instrumented → no line, no 0).
- [x] 5.6 privacy fuzz: sensitive server + tool segment + raw
  `mcp__` never on any surface/log; only the integer moves.
- [x] 5.7 Reconciled — see R7/§6.2: capture-time opt-out gate dropped
  to match the v3.1/v3.2 pattern (allowlist reduction is the
  unconditional privacy boundary); no inconsistent bespoke gate.

## 6. Spec sync (close-out, same session as code)

- [x] 6.1 Ticked incrementally (not batched).
- [x] 6.2 Phase-0 findings + the R7 opt-out deviation recorded in
  `design.md`.
- [x] 6.3 Roadmap entry 57 added with final test count + trio status.
- [x] 6.4 Archived to
  `openspec/changes/archive/2026-05-18-v3.4-mcp-inventory/`.
