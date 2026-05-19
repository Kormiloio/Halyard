# Tasks

Implementation checklist for v3.4 — MCP-server usage inventory.

## 0. Prerequisites

- [x] 0.1 v3.0–v3.2 complete.
- [ ] 0.2 **Phase-0 spike (gating)** — S1 (`mcp__<server>__<tool>`
  convention per collector; separator/escaping) and S2 (no builtin
  tool name collides with the `mcp__` prefix). Append findings to
  `design.md`. §3 collector code blocked until checked. The privacy
  model is fixed by the proposal — NOT part of the spike.

## 1. Privacy primitive (shared, test-first)

- [ ] 1.1 `MCP_SERVER_ALLOWLIST` frozenset + `reduce_mcp(names:
  set[str]) -> tuple[int, str | None]` in a shared module
  (`leverage.py` or a small `mcp_inventory.py`): count + allowlisted
  sorted comma string; fail-closed on empty.
- [ ] 1.2 `extract_mcp_server(tool_name: str) -> str | None` — exact
  `mcp__` prefix + `__` delimiter anchor; None on any non-match or
  malformed (no partial).
- [ ] 1.3 Unit-test 1.1/1.2 before any collector wiring (allowlist
  boundary, non-allowlisted counted-not-named, garbled → None).

## 2. Schema & log

- [ ] 2.1 `db.py` migration `(5,…)`: two additive `ALTER TABLE
  sessions` columns; `_CURRENT_VERSION` 5→6; `_CREATE_SCHEMA_V1`
  sessions block updated; idempotent self-heal verified.
- [ ] 2.2 `AiSession.mcp_servers_used: int | None`,
  `mcp_server_names: str | None`; `to_log_line` + `_parse_line_result`
  round-trip; empty case byte-identical to v3.2 (v2.75 path intact).

## 3. Collector wiring (gated on §0.2)

- [ ] 3.1 Claude Code: in the existing `tool_use` loop, read `name`,
  collect distinct servers via 1.2, set fields via 1.1 at close. Do
  not perturb v3.2 tool-call/error counts.
- [ ] 3.2 Other collectors per S1: wire where tool names are visible;
  leave fields unset otherwise (honest absence, R5). Partial rollout
  is acceptable and explicitly tested.

## 4. Surface (Leverage parity)

- [ ] 4.1 Shared `leverage` MCP rollup (distinct allowlisted names +
  max distinct count over the window).
- [ ] 4.2 Web `_leverage_panel` + TUI `LeveragePane`: one identical
  capability line, only when data exists; "+N" for unnamed
  (non-allowlisted) servers per R6.
- [ ] 4.3 Absent → byte-identical to v3.2 (both surfaces). Report &
  invoice untouched.

## 5. Tests (≥15)

- [ ] 5.1 `extract_mcp_server` + `reduce_mcp` units incl. allowlist
  boundary, garbled, empty, non-allowlisted-counted-not-named.
- [ ] 5.2 Round-trip + byte-stable empty case (v2.75 unaffected).
- [ ] 5.3 Additive migration v5→v6, no reset, idempotent.
- [ ] 5.4 Web↔TUI parity; absent → v3.2-identical; "+N" rendering.
- [ ] 5.5 Partial-rollout honesty (a non-instrumented collector never
  implies "0 servers").
- [ ] 5.6 Privacy fuzz (R8): sensitive server name + args → only the
  integer moves; name/args appear in no surface/log/cache.
- [ ] 5.7 Opt-out (`[outcomes] enabled = false`) suppresses all of it.

## 6. Spec sync (close-out, same session as code)

- [ ] 6.1 Tick this file as items land (not batched).
- [ ] 6.2 Record Phase-0 findings in `design.md`; note any deviation.
- [ ] 6.3 Roadmap entry 57 in `openspec/project.md` with final test
  count; mark the v3.0-deferred trio status (rejection = v3.3
  feasibility-gated; MCP usage = done; MCP availability = still
  deferred).
- [ ] 6.4 Archive to
  `openspec/changes/archive/YYYY-MM-DD-v3.4-mcp-inventory/`.
