"""Halyard CLI entry point."""

from __future__ import annotations

from datetime import datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

import typer
from rich.console import Console

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="halyard",
    help="AI work intelligence infrastructure. Plain text. Owned by you.",
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"halyard {pkg_version('halyard')}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Drop into the interactive REPL when invoked with no subcommand."""
    if ctx.invoked_subcommand is None:
        from halyard.ai_log import find_project_dir
        from halyard.repl import run_repl

        project_dir = find_project_dir()
        if project_dir is None:
            console.print(
                "[bold red]Error:[/] No Halyard project found. "
                "Run [bold]halyard init[/] to create one."
            )
            raise typer.Exit(code=1)

        run_repl(project_dir)


# ---------------------------------------------------------------------------
# Top-level command groups (register pattern)
# ---------------------------------------------------------------------------

from halyard import cli_hooks, cli_importers, cli_org, cli_report, cli_session, cli_setup  # noqa: E402, I001

cli_hooks.register(app)
cli_setup.register(app)
cli_session.register(app)
cli_importers.register(app)
cli_report.register(app)
cli_org.register(app)


# ---------------------------------------------------------------------------
# Sub-app command groups (Typer sub-apps — Phase 1)
# ---------------------------------------------------------------------------

from halyard import cli_config, cli_db, cli_outcome, cli_projects, cli_service, cli_voyage  # noqa: E402, I001

app.add_typer(cli_service.app)
app.add_typer(cli_config.app)
app.add_typer(cli_db.app)
app.add_typer(cli_projects.app)
app.add_typer(cli_voyage.app)
app.add_typer(cli_outcome.app)


# ---------------------------------------------------------------------------
# Easter eggs
# ---------------------------------------------------------------------------


@app.command(hidden=True)
def ahoy() -> None:
    """⚓  Ahoy, Captain."""
    from halyard.easter_eggs import random_quote, ship_art

    typer.echo(ship_art())
    typer.echo(f'  "{random_quote()}"')
    typer.echo("\n  Fair winds and following seas. 🌊\n")


@app.command(hidden=True)
def mayday() -> None:
    """🆘  Send a distress signal."""
    from halyard.easter_eggs import mayday_lines

    for line in mayday_lines():
        typer.echo(line)


@app.command(hidden=True)
def signal(
    code: str = typer.Argument(..., help="0/1 Morse code (START=0001010101, STOP=00011110110)"),
    slug: str = typer.Argument("", help="client/project slug for start signal"),
) -> None:
    """📡  Decode a 0/1 Morse signal and fire timer start or stop."""
    from halyard.easter_eggs import MORSE_START, MORSE_STOP, morse_timer_action

    action = morse_timer_action(code)

    if action is None:
        console.print("[yellow]📡 Unknown signal.[/] Recognized codes:")
        console.print(f"   START: [bold]{MORSE_START}[/]  [dim](· · ·  —  · —  · — ·  —)[/]")
        console.print(f"   STOP:  [bold]{MORSE_STOP}[/]  [dim](· · ·  —  — — —  · — — ·)[/]")
        return

    console.print(f"[bold cyan]📡  · · ·  — — —  · · ·[/]  Signal: [bold]{action.upper()}[/]")

    if action == "stop":
        from halyard.orchestration import stop_timer
        from halyard.reports import _elapsed_minutes, format_minutes, read_active_timer

        active = read_active_timer()
        if active is None:
            console.print("[red]No active timer to stop.[/]")
            return
        result = stop_timer(Path.cwd())
        try:
            from halyard.auto_timer import auto_timer_close_now

            auto_timer_close_now()
        except Exception:
            pass
        if result.was_running:
            from halyard.visuals import stop_card

            now = datetime.now()
            started = active.started or now.strftime("%Y-%m-%d %H:%M:%S")
            elapsed_mins = _elapsed_minutes(started, now)
            elapsed = format_minutes(elapsed_mins)
            console.print(stop_card(active.slug, elapsed_mins, elapsed, result.backfill_count))

    elif action == "start":
        if not slug:
            console.print("[yellow]⚓ START signal received.[/] Provide a slug to begin:")
            console.print(f"   [bold]halyard signal {MORSE_START} client/project[/]")
            return
        from halyard.orchestration import TimerAlreadyRunning, start_timer

        timeclock_candidate = Path.cwd() / "time.timeclock"
        if not timeclock_candidate.exists():
            console.print("[red]No time.timeclock here. Run [bold]halyard init[/] first.[/]")
            return
        account = slug.replace("/", ":", 1)
        try:
            timer = start_timer(Path.cwd(), account)
        except TimerAlreadyRunning as e:
            console.print(f"[red]Timer already running for [bold]{e.slug}[/].[/]")
            return
        console.print(f"[green]Started[/] [bold]{timer.slug}[/] at {timer.started}.")


if __name__ == "__main__":
    app()
