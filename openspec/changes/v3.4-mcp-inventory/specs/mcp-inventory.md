# Spec: MCP-server usage inventory

WHEN/THEN requirements. Extends — never weakens — the v3.0 privacy
contract. Counts/allowlisted-names only.

## R1 — Usage derivation

- WHEN a collector parses a tool call whose name matches
  `mcp__<server>__<tool>`, THEN `<server>` is added to that session's
  distinct-MCP-server set.
- WHEN a tool name does not match the exact `mcp__` prefix + `__`
  server delimiter, THEN it contributes nothing (it is a normal tool).
- WHEN a name matches the prefix but the server segment is empty or
  unparseable, THEN it is ignored entirely (fail-closed) — never a
  partial or guessed server.

## R2 — Privacy reduction (in the collector, before any write)

- WHEN a session's distinct-server set is finalized, THEN
  `mcp_servers_used` = the integer cardinality of that set.
- WHEN building `mcp_server_names`, THEN it contains ONLY the members
  of the set that are in `MCP_SERVER_ALLOWLIST`, sorted and
  comma-joined; non-allowlisted members are excluded from the string
  but still counted in `mcp_servers_used`.
- WHEN no MCP tool was used, THEN both fields are absent (None) — never
  `0`/empty-string written.
- WHEN any value is written or rendered, THEN the raw `mcp__*__*`
  string, the tool segment, tool arguments, server command, URL, env,
  and any non-allowlisted server name MUST NOT appear anywhere (log,
  cache, report, panel, invoice, egress).

## R3 — Allowlist is a fixed public constant

- WHEN the allowlist is consulted, THEN it is the in-repo
  `MCP_SERVER_ALLOWLIST` frozenset; there is no runtime/config/env
  source for it. Extending it is a code change under review.

## R4 — Schema & log are additive

- WHEN a v5 cache is opened by v3.4, THEN the `(5,…)` migration adds
  `mcp_servers_used` / `mcp_server_names` to `sessions`, existing rows
  read back NULL, and no `db reset` is required.
- WHEN a session with no MCP usage is serialized, THEN `to_log_line()`
  is byte-identical to v3.2 (no empty MCP tokens; v2.75 extensible
  path unaffected).
- WHEN a session with MCP usage round-trips through
  `to_log_line` → `from_log_line`, THEN both fields are preserved
  exactly.

## R5 — Partial collector rollout is honest

- WHEN a collector has no tool-name visibility (Phase-0 S1), THEN it
  sets neither field; surfaces show MCP data only for sessions that
  have it and never imply "0 servers" for sessions that simply weren't
  instrumented.

## R6 — Surface (Leverage parity only)

- WHEN the Leverage panel renders (web or TUI) AND ≥1 session in the
  window has `mcp_servers_used`, THEN one capability line is shown,
  derived from the shared summary, identical text in both surfaces.
- WHEN no session has MCP data, THEN both surfaces are byte-identical
  to v3.2 (no MCP line).
- WHEN the capability line shows server names, THEN it shows only
  allowlisted names; the count may exceed the number of names shown
  (non-allowlisted servers counted but unnamed) and the line makes
  that explicit (e.g. "MCP: 4 servers (github, filesystem +2)").
- WHEN the outcome report or invoice appendix renders, THEN it is
  byte-identical to v3.2 (MCP is neither per-PR nor client-facing).

## R7 — Opt-out

- WHEN `[outcomes] enabled = false`, THEN no MCP fields are populated
  and no MCP line renders, exactly as for the other outcome signals.

## R8 — Privacy fuzz

- WHEN the fuzz suite seeds a sensitive non-allowlisted server name
  (e.g. `mcp__acme_secret_internal__op`) and arbitrary tool args into
  a session, THEN the only observable effect on any surface/log/cache
  is `mcp_servers_used` incrementing; the sensitive name and args
  appear nowhere.
