# Design: v3.4 — MCP-server usage inventory

## Phase-0 spike (gating — resolve before collector code)

Partially answered by the audit; the rest is a small read-only spike.

**Answered (2026-05-18 audit):**
- Claude Code transcript `tool_use` blocks are already iterated in
  `claude_code.py` (the v3.2 tool-call counting loop). The block's
  `name` field is *not* read today. An MCP tool is named
  `mcp__<server>__<tool>` (Claude Code convention). So Claude Code MCP
  *usage* is one `.get("name")` away inside an existing loop.

**Spike S1 — prefix convention per collector.** Confirm the
`mcp__<server>__<tool>` naming holds for Cursor and Codex tool-call
records too, and document the exact separator/escaping. If a collector
uses a different convention (or doesn't expose tool names), it is a
*partial-rollout* collector — the count is simply absent for it
(v3.2-style honest absence), never guessed.

**Spike S2 — prefix collision.** Confirm no non-MCP builtin tool name
begins with `mcp__`. The extractor must anchor on the exact prefix and
the double-underscore server delimiter, and ignore any malformed name
(fail-closed: unparseable name → not counted, never partially counted).

**Exit criterion:** S1/S2 findings appended here as "Phase-0
findings". Collector tasks (§3) blocked until then. The privacy model
(§ below) is fixed by the proposal and is *not* part of the spike.

## Privacy model (the contract extension)

This changeset extends the v3.0 privacy contract with one clause,
modelled exactly on `shell_history`'s allowlist→count:

```
MCP_SERVER_ALLOWLIST = frozenset({
    "github", "filesystem", "fetch", "git", "sqlite", "postgres",
    "puppeteer", "playwright", "slack", "sentry", "memory", "time",
    "everything", "brave-search", "gdrive", "notion",
})  # fixed, public, in-repo; extending = reviewed code change
```

Reduction pipeline, applied **in the collector before anything is
written**:

```
tool_use.name = "mcp__acme_internal_billing__charge"
  → split on "mcp__", take server segment up to next "__"
  → server = "acme_internal_billing"
  → distinct servers this session: {github, acme_internal_billing}
  → mcp_servers_used = 2                       # always
  → mcp_server_names  = "github"               # allowlisted only
     (acme_internal_billing is counted, never named)
```

Invariants (pinned by spec + fuzz test):
- The raw `mcp__*__*` string, the tool segment, args, server
  command/URL/env are **never** read beyond the server-segment split,
  and never stored/logged/egressed.
- A non-allowlisted server contributes **only** to the integer.
- Empty/garbled name → ignored (fail-closed), never a partial token.
- `mcp_server_names` is sorted + comma-joined for byte-stable output.

## Schema & log

- Additive migration `(5, …)` in `db.py` (v3.1 left at v5):
  `ALTER TABLE sessions ADD COLUMN mcp_servers_used INTEGER;`
  `ALTER TABLE sessions ADD COLUMN mcp_server_names TEXT;`
  `_CURRENT_VERSION` 5→6; `_CREATE_SCHEMA_V1` sessions block updated.
- Two optional `AiSession` fields (`int | None`, `str | None`); emitted
  in `to_log_line` and parsed in `_parse_line_result`; v2.75
  extensible-token path must stay byte-stable for the empty case
  (regression-tested, as v3.1 did).

## Collector wiring

- **Claude Code first** (loop exists): in the `tool_use` iteration,
  also read `name`; feed a per-session `set[str]` through the reduction
  pipeline; set the two fields at session close. Tool-call counting
  (v3.2) is untouched.
- Other collectors: gated on S1. Each lands independently; a collector
  without tool-name visibility simply never sets the fields (honest
  absence — no "0 servers" claim).

## Surface

- Shared `leverage`: add a windowed MCP rollup (distinct allowlisted
  server names seen + the max distinct-server count over the window)
  to the existing summary path so
  web (`_leverage_panel`) and TUI (`LeveragePane`) render one identical
  capability line, only when ≥1 session has the data. Absent →
  byte-identical to v3.2 (same guarantee/test pattern as v3.1/v3.2).
- Outcome report: **unchanged** (capability is not per-PR).
- Invoice appendix: **unchanged** (not client-facing).

## Alternatives considered

- **Hash non-allowlisted server names** (like v3.0 file-path hashing)
  instead of dropping them. Rejected for v3.4: a hash is still a stable
  per-server identifier (re-identifiable across sessions) for zero
  added user value here — the integer count carries the signal. Drop,
  don't hash. (Revisit only if per-server correlation is ever specced.)
- **Capture availability (configured servers) too.** Rejected: needs
  reading MCP config files = commands/URLs/env in scope = a far larger
  privacy surface. Separate future changeset; v3.4 is usage-only.
- **Store the count via v2.75 `extra` passthrough** instead of a typed
  field. Rejected: this is first-class capability data the OSS should
  interpret; `extra` is for *un*interpreted forward-compat tokens.

## Risks

| Risk | Mitigation |
|---|---|
| Non-allowlisted server name leaks | Reduction in collector pre-write; fuzz test seeds a sensitive server name and asserts only the count moves |
| `mcp__` prefix collision with a builtin | S2 spike; exact-prefix + delimiter anchor; fail-closed on malformed |
| Web/TUI drift | Single shared summary; parity test (v3.1/v3.2 pattern) |
| Scope creep into availability/config | Success criterion + explicit out-of-scope; no config read in code |
| Allowlist becomes a maintenance sink | Fixed small public set; extension = reviewed PR, same as shell_history |
