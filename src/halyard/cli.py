"""Halyard CLI entry point.

This module defines the command surface for v0. Each command currently raises
NotImplementedError pointing at the task in
`openspec/changes/v0-time-and-invoice/tasks.md` that will fill it in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console

# ---------------------------------------------------------------------------
# Default file contents written by `halyard init`
# ---------------------------------------------------------------------------

_HALYARD_TOML_TEMPLATE = """\
[business]
name = "{business_name}"
currency = "USD"
default_due_days = 30

[invoicing]
counter = 0
prefix = "{{year}}-{{month:02d}}-{{client_slug}}"
"""

_CLIENTS_TOML = """\
# Add your clients here — one [[client]] block per client.
#
# [[client]]
# slug = "acme"            # required; lowercase letters, digits, hyphens
# name = "Acme Corp"       # required; display name on invoices
# hourly_rate = 150        # required; numeric, in the project currency
# email = "ap@acme.com"    # optional
# address = \"\"\"           # optional; multi-line OK
# 123 Main St
# Anytown, ST 12345
# \"\"\"
"""

_PROJECTS_TOML = """\
# Add your projects here — one [[project]] block per project.
#
# [[project]]
# slug = "auth-migration"   # required; scoped under the client
# client_slug = "acme"      # required; must match a slug in clients.toml
# name = "Auth migration"   # required; display name on invoices
# hourly_rate = 175         # optional; overrides the client rate for this project
"""

_TIMECLOCK = """\
; Halyard timeclock — hledger-compatible
; i YYYY-MM-DD HH:MM:SS client:project  optional comment
; o YYYY-MM-DD HH:MM:SS
"""

_GITIGNORE = """\
# Halyard
.halyard-cache/
.DS_Store

# Uncomment the line below to keep generated PDFs out of version control.
# invoices/*.pdf
"""


def _detect_business_name() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        name = result.stdout.strip()
        if name:
            return f"{name} Consulting"
    except Exception:
        pass
    return "Your Name Consulting"


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
    cwd = Path.cwd()
    config_file = cwd / "halyard.toml"

    if config_file.exists():
        console.print(
            "[bold red]Error:[/] [bold]halyard.toml[/] already exists here.\n"
            "Remove or move it before re-initializing."
        )
        raise typer.Exit(code=1)

    halyard_toml = _HALYARD_TOML_TEMPLATE.format(business_name=_detect_business_name())
    config_file.write_text(halyard_toml)
    (cwd / "clients.toml").write_text(_CLIENTS_TOML)
    (cwd / "projects.toml").write_text(_PROJECTS_TOML)
    (cwd / "time.timeclock").write_text(_TIMECLOCK)
    (cwd / "invoices").mkdir(exist_ok=True)
    (cwd / ".gitignore").write_text(_GITIGNORE)

    console.print("[bold green]Halyard project initialized.[/]\n")
    console.print("Next steps:")
    console.print("  1. Edit [bold]halyard.toml[/] — confirm your business name and currency.")
    console.print("  2. Edit [bold]clients.toml[/] — add your first client with an hourly rate.")
    console.print("\nMore commands coming: halyard log, halyard start/stop, halyard invoice.")


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
    month: str | None = typer.Option(None, "--month", help="last | this | YYYY-MM"),
    from_: str | None = typer.Option(None, "--from", help="ISO date (inclusive lower bound)"),
    to: str | None = typer.Option(None, "--to", help="ISO date (inclusive upper bound)"),
) -> None:
    """Generate an invoice from logged time entries."""
    raise NotImplementedError("v0 task 4.2")


if __name__ == "__main__":
    app()
