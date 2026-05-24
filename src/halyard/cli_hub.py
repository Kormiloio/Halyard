"""halyard hub — background daemon management sub-commands."""

from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="hub", help="Manage the Halyard Hub (central telemetry daemon).")


@app.command(name="start")
def hub_start(
    project_dir: Path = typer.Option(None, "--project-dir", help="Project directory for the hub."),
    port: int | None = typer.Option(
        None, "--port", help="Port for the OTLP/Hub receiver (default: HALYARD_HUB_PORT or 4318)."
    ),
    foreground: bool = typer.Option(False, "--foreground", help="Run in the foreground."),
) -> None:
    """Start the Halyard Hub daemon."""
    from halyard.hub_client import hub_port
    from halyard.hub_server import HubServer

    if port is None:
        port = hub_port()
    server = HubServer(project_dir=project_dir, port=port)

    if foreground:
        console.print(f"[bold green]Starting Halyard Hub[/] on 127.0.0.1:{port} (foreground)...")
        try:
            server.start()
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
            console.print("[yellow]Hub stopped.[/]")
    else:
        # In a real implementation, we'd daemonize here or rely on the service manager.
        # For now, we support the 'service install' path which runs in foreground.
        console.print(
            "[red]Error:[/] Use [bold]halyard service install[/] for background execution."
        )
        raise typer.Exit(code=1)


@app.command(name="status")
def hub_status() -> None:
    """Check if the Halyard Hub is reachable."""
    from halyard.hub_client import hub_url, ping

    url = hub_url()
    if ping():
        console.print(f"[bold green]Running[/]  {url}")
    else:
        console.print(f"[yellow]Stopped[/]  ({url} unreachable)")


def register(main_app: typer.Typer) -> None:
    main_app.add_typer(app)
