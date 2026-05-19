# Proposal: v3.4 — MCP-server usage inventory (privacy-first)

## Why

Halyard records *what* AI work happened, whether it shipped (v3.0),
what review cost (v3.1), and how much it thrashed (v3.2). It has no
view of *capability context* — which MCP servers the AI actually used
in a session. That context matters for the leverage story: "sessions
that used the `github` MCP server merged 2× more often" is the kind of
capability→outcome link a CTO asks about, and it is the last of the
three v3.0-deferred signals.

This is greenfield (no field, no capture path today). But a Phase-0
audit found the *usage* signal is already inside the Claude Code parse
loop: `tool_use` blocks are iterated today and an MCP tool is named
`mcp__<server>__<tool>`. So MCP **usage** inventory is largely a v3.2-
shaped "read a field already in the loop" change — *if* the privacy
model is right. **Privacy is the dominant design concern of this
changeset, not the plumbing.**

## Scope: usage, not availability

- **In scope — MCP usage:** which MCP servers had at least one tool
  invoked in the session, reduced immediately to a privacy-safe form
  (see below). Derived from tool-call names already parsed.
- **Out of scope — MCP availability:** servers *configured but unused*
  (would require reading each tool's MCP config / `.mcp.json` /
  settings — a new capture path with a much larger privacy surface:
  commands, URLs, env, args). Explicitly deferred to a later
  changeset. v3.4 never reads MCP config.
- **Out of scope:** MCP tool *arguments*, server URLs/commands/env, or
  the specific tool names — only the *server* segment, privacy-reduced.

## The privacy model (load-bearing)

An MCP server identifier is user-chosen and can itself be sensitive
(e.g. `acme-internal-billing`). Following the v3.0 privacy contract
(integers/enums only, fail-closed, opt-out) and the `shell_history`
precedent (allowlist → count, never raw), v3.4 stores:

1. **`mcp_servers_used`** — an integer count of *distinct* MCP servers
   whose tools were invoked. Always safe; primary signal.
2. **`mcp_server_names`** — OPTIONAL, and only the subset of server
   names on a small, well-known **public allowlist** (e.g. `github`,
   `filesystem`, `fetch`, `sqlite`, `puppeteer`, `slack`, `sentry` …).
   Any server not on the allowlist is **not named** — it only
   contributes to the integer count. Identical model to the
   `shell_history` canonical-command allowlist.

Never stored, never logged, never egressed: the full `mcp__x__y`
string, tool names, arguments, server commands, URLs, env, or any
non-allowlisted server name. The allowlist is a fixed, public,
in-repo constant — extending it is a reviewed code change, exactly
like the shell-history allowlist.

## What changes

- One Phase-0 spike (see `design.md`): confirm the `mcp__<server>__`
  tool-name convention per collector and that non-MCP tools never
  collide with the prefix.
- Two new optional `AiSession` fields: `mcp_servers_used: int | None`
  and `mcp_server_names: str | None` (comma-joined allowlisted names,
  sorted). New `a`/`s` log tokens (v2.75 extensible-token safe).
- Additive SQLite migration (v5 → v6) — two nullable columns; no reset.
- Collectors populate the count from tool-call names they already
  parse (Claude Code first — the loop already exists; others gated on
  the Phase-0 per-collector confirmation, partial rollout is fine).
- Surface: a one-line capability note on the Leverage panel
  (web + TUI parity via shared `leverage`) — "MCP: N servers used
  (github, filesystem)" — only when data exists; absent →
  byte-identical to v3.2. Outcome report and invoice appendix
  unchanged (capability is not a per-PR or client signal).

## What stays the same

- Plain-text log is the source of truth; new tokens are additive and
  optional. v3.0 privacy contract holds verbatim; this changeset
  *extends* it with the allowlist clause, it does not weaken it.
- Opt-out: the existing `[outcomes] enabled = false` also disables MCP
  inventory (it is outcome-adjacent capability metadata).
- No new network, no config reading, no phone-home.

## Out of scope

- MCP availability/config inventory (deferred — new capture surface).
- Per-server outcome correlation ("github-using sessions merge more")
  — a later analysis changeset once the inventory exists.
- Non-allowlisted server names in any form.

## Prerequisites

- v3.0–v3.2 complete (they are).
- Phase-0 per-collector tool-name spike (in `design.md`) resolved
  before collector code lands. The privacy model (allowlist + count)
  is fixed by this proposal and is the alignment gate.

## Success criteria

1. `mcp_servers_used` is an integer; `mcp_server_names` contains only
   allowlisted names; a fuzz test proves no `mcp__*__*` string, tool
   name, arg, URL, or non-allowlisted server name reaches the log,
   cache, or any surface.
2. A session using a non-allowlisted server increments the count but
   contributes no name.
3. Leverage panel shows the capability line only when data exists;
   web and TUI show identical text; absent → v3.2-identical.
4. Additive migration (v5→v6), no reset; v2.75 extensible-token path
   unaffected.
5. ≥15 tests incl. the allowlist boundary, the privacy fuzz, web/TUI
   parity, absent-path, and the migration.

## Strategic implication

Completes the v3.0-deferred trio (rejection capture is feasibility-
gated in v3.3; this is the cleaner of the two). It adds the
*capability* axis to the leverage story without reading a single MCP
config file or storing one server URL — capability context at zero new
sensitive-data egress.

## Detailed design

See `design.md`.
