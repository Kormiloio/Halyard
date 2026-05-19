"""v3.4 — MCP-server *usage* inventory, privacy-first.

A tool provided by an MCP server is named ``mcp__<server>__<tool>``.
This module turns the set of MCP tool names seen in a session into two
privacy-bounded values:

- ``mcp_servers_used`` — an integer count of distinct servers. Always
  safe; the primary signal.
- ``mcp_server_names`` — ONLY the subset of server names on a fixed,
  public, in-repo allowlist (same model as ``shell_history``'s
  canonical-command allowlist). A non-allowlisted server is counted but
  never named, logged, or egressed.

The raw ``mcp__*__*`` string, the tool segment, arguments, and any
server command/URL/env are never read beyond the server-segment split
and never stored. Malformed names fail closed (ignored entirely).
"""

from __future__ import annotations

# Fixed, public, in-repo. Extending this is a reviewed code change —
# exactly like the shell_history canonical-command allowlist. Only
# widely-known public MCP servers belong here; anything user-specific
# stays an integer-only count.
MCP_SERVER_ALLOWLIST = frozenset(
    {
        "github",
        "filesystem",
        "fetch",
        "git",
        "sqlite",
        "postgres",
        "puppeteer",
        "playwright",
        "slack",
        "sentry",
        "memory",
        "time",
        "everything",
        "brave-search",
        "gdrive",
        "notion",
    }
)

_PREFIX = "mcp__"
_DELIM = "__"


def extract_mcp_server(tool_name: str | None) -> str | None:
    """Return the server segment of an ``mcp__<server>__<tool>`` name.

    Anchored on the exact prefix and the ``__`` server/tool delimiter.
    Returns None for any non-MCP name or malformed input (fail-closed:
    a partial or ambiguous name yields nothing, never a guess).
    """
    if not tool_name or not tool_name.startswith(_PREFIX):
        return None
    rest = tool_name[len(_PREFIX) :]
    delim = rest.find(_DELIM)
    if delim <= 0:
        # No tool segment, or an empty server segment ("mcp____tool").
        return None
    server = rest[:delim]
    return server or None


def reduce_mcp(servers: set[str]) -> tuple[int | None, str | None]:
    """Reduce a session's distinct-server set to the two stored values.

    Returns ``(mcp_servers_used, mcp_server_names)``:
    - count is the integer cardinality, or None when the set is empty
      (absent, never a written 0);
    - names is the sorted, comma-joined subset that is on the
      allowlist, or None when no member is allowlisted.
    """
    if not servers:
        return None, None
    count = len(servers)
    named = sorted(s for s in servers if s in MCP_SERVER_ALLOWLIST)
    return count, (",".join(named) if named else None)
