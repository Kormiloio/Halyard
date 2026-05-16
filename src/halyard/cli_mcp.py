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
