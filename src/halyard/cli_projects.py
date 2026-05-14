"""halyard projects — project registry sub-commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="projects", help="Manage the Halyard project registry.")


@app.command(name="list")
def projects_list() -> None:
    """List all registered Halyard project directories."""
    from halyard.registry import REGISTRY_PATH, read_registry, stale_paths

    valid = read_registry()
    stale = stale_paths()

    if not valid and not stale:
        console.print(
            "[yellow]No projects registered.[/] Run [bold]halyard init[/] in a project directory."
        )
        return

    console.print(f"[bold]Halyard project registry[/]  [dim]{REGISTRY_PATH}[/]\n")
    for p in valid:
        console.print(f"  [green]✓[/]  {p}")
    for p in stale:
        console.print(f"  [yellow]✗[/]  {p}  [dim](not found — run halyard projects forget)[/]")


@app.command(name="forget")
def projects_forget(
    path: str = typer.Argument(..., help="Absolute path of the project to remove."),
) -> None:
    """Remove a project from the registry (does not delete files)."""
    from halyard.registry import forget_project

    removed = forget_project(Path(path))
    if removed:
        console.print(f"[bold green]Removed[/] {path} from registry.")
    else:
        console.print(f"[yellow]{path}[/] was not in the registry.")


@app.command(name="add")
def projects_add(
    path: str = typer.Argument(..., help="Absolute path of an existing Halyard project."),
) -> None:
    """Explicitly add an existing Halyard project directory to the registry."""
    from halyard.registry import add_project

    ok = add_project(Path(path))
    if ok:
        console.print(f"[bold green]Registered[/] {path}")
    else:
        console.print(
            f"[bold red]Error:[/] {path} does not exist or has no halyard.toml. "
            "Run [bold]halyard init[/] there first."
        )
        raise typer.Exit(code=1)
