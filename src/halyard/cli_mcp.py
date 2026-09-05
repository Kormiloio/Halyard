"""halyard mcp — run the read-only MCP server over stdio."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()


def register(app: typer.Typer) -> None:
    @app.command(name="mcp")
    def mcp() -> None:
        """Run the Halyard MCP server (stdio) for Claude Code / Cursor.

        Read-only: exposes the aggregate ledger to MCP clients. Requires
        the optional MCP extra: pip install 'halyard[mcp]'.
        """
        from halyard.mcp_server import build_server

        try:
            # build_server() lazily imports the optional `mcp` SDK.
            server = build_server()
        except ModuleNotFoundError as exc:
            # An incompatible SDK raises ModuleNotFoundError too: mcp 2.x
            # renamed FastMCP -> MCPServer, so `mcp.server.fastmcp` is
            # simply absent. Reporting that as "not installed" sends the
            # user to reinstall an extra they already have — and the
            # reinstall resolves 2.x again, reproducing the same message.
            #
            # Discriminate on which module was missing, not on whether
            # `mcp` is importable: a *submodule* miss means the package is
            # present but wrong-major. exc.name is set by the import
            # system even when the SDK raises its own guidance message.
            # Unknown (name is None) falls through to "not installed",
            # the commoner case.
            missing = exc.name or ""
            if missing.startswith("mcp."):
                console.print(
                    r"[bold red]Error:[/] the installed MCP SDK is not compatible."
                    "\n"
                    f"{exc}"
                    "\n"
                    r"Halyard needs mcp 1.x: [bold]pip install 'mcp>=1.28.1,<2'[/]"
                )
            else:
                console.print(
                    r"[bold red]Error:[/] the MCP SDK is not installed."
                    "\n"
                    r"Install it with:  [bold]pip install 'halyard\[mcp]'[/]"
                    r"  (or  [bold]uv tool install 'halyard\[mcp]'[/])"
                )
            raise typer.Exit(code=1) from exc

        # FastMCP defaults to stdio transport — the MCP client spawns
        # this process per session; nothing long-lived.
        server.run()
