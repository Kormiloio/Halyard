"""Halyard CLI entry point.

This module defines the command surface for v0. Each command currently raises
NotImplementedError pointing at the task in
`openspec/changes/v0-time-and-invoice/tasks.md` that will fill it in.
"""
from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="halyard",
    help=(
        "Plain-text, agent-native financial OS. "
        "Your books in plain text. Owned by you. Operated by Claude."
    ),
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    """Drop into the interactive Claude REPL when invoked with no subcommand."""
    if ctx.invoked_subcommand is None:
        # TODO(v0 task 5.4): launch interactive agent REPL.
        console.print(
            "[bold cyan]Halyard[/] — interactive REPL not yet implemented "
            "(see openspec/changes/v0-time-and-invoice/tasks.md task 5.4)."
        )
        raise typer.Exit(code=1)


@app.command()
def init() -> None:
    """Scaffold a new Halyard project in the current directory."""
    raise NotImplementedError("v0 task 2.3")


@app.command()
def log(
    message: str = typer.Argument(..., help="Natural-language description of work."),
) -> None:
    """Log time from a free-form description (calls Claude to extract the entry)."""
    raise NotImplementedError("v0 task 3.2")


@app.command()
def start(
    slug: str = typer.Argument(..., help="client/project slug, e.g. acme/auth-migration"),
) -> None:
    """Start the active timer."""
    raise NotImplementedError("v0 task 3.1")


@app.command()
def stop() -> None:
    """Stop the active timer."""
    raise NotImplementedError("v0 task 3.1")


@app.command()
def invoice(
    client: str = typer.Argument(..., help="Client slug to invoice."),
    month: str | None = typer.Option(
        None, "--month", help="last | this | YYYY-MM"
    ),
    from_: str | None = typer.Option(
        None, "--from", help="ISO date (inclusive lower bound)"
    ),
    to: str | None = typer.Option(
        None, "--to", help="ISO date (inclusive upper bound)"
    ),
) -> None:
    """Generate an invoice from logged time entries."""
    raise NotImplementedError("v0 task 4.2")


if __name__ == "__main__":
    app()
