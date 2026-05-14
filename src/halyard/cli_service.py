"""halyard service — macOS LaunchAgent management sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()

app = typer.Typer(
    name="service", help="Manage the Halyard Glass Cockpit background service."
)


@app.command(name="install")
def service_install(
    port: int = typer.Option(7432, "--port", help="Port for the background dashboard."),
) -> None:
    """Install Halyard as a macOS login service (auto-starts the Glass Cockpit)."""
    import platform

    if platform.system() != "Darwin":
        console.print("[bold red]Error:[/] Service management is only supported on macOS.")
        raise typer.Exit(code=1)

    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.service import install_service

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print(
            "[bold red]Error:[/] No Halyard project or hub found. "
            "Run [bold]halyard init[/] or [bold]halyard set-hub[/] first."
        )
        raise typer.Exit(code=1)

    try:
        url = install_service(project_dir, port=port)
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold green]Service installed.[/] Glass Cockpit will start at login.")
    console.print(f"  Dashboard: [bold cyan]{url}[/]")
    console.print("  Logs:      ~/Library/Logs/halyard-dashboard.log")
    console.print("\nTo uninstall: [bold]halyard service uninstall[/]")


@app.command(name="uninstall")
def service_uninstall() -> None:
    """Uninstall the Halyard background service."""
    import platform

    if platform.system() != "Darwin":
        console.print("[bold red]Error:[/] Service management is only supported on macOS.")
        raise typer.Exit(code=1)

    from halyard.service import PLIST_PATH, uninstall_service

    if not PLIST_PATH.exists():
        console.print("[yellow]Service is not installed.[/]")
        return

    uninstall_service()
    console.print("[bold green]Service uninstalled.[/]")


@app.command(name="status")
def service_status_cmd() -> None:
    """Show whether the Halyard background service is running."""
    import platform

    if platform.system() != "Darwin":
        console.print("[bold red]Error:[/] Service management is only supported on macOS.")
        raise typer.Exit(code=1)

    from halyard.service import service_status

    running, info = service_status()
    if running:
        console.print(f"[bold green]Running[/]  {info}")
    else:
        console.print(f"[yellow]Stopped[/]  {info}")
