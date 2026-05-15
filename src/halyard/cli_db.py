"""halyard db — SQLite read-model cache sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="db", help="SQLite cache management.")


@app.command(name="sync")
def db_sync(
    status: bool = typer.Option(False, "--status", help="Show last sync status without syncing."),
) -> None:
    """Sync plain-text log files into the SQLite cache (~/.halyard/cache.db)."""
    from halyard.db import db_path, last_sync, sync_all

    if status:
        info = last_sync()
        if info is None:
            console.print("[yellow]Never synced.[/] Run [bold]halyard db sync[/] first.")
        else:
            console.print(f"[bold]Last sync:[/] {info['synced_at']}")
            console.print(f"  Files read:  {info['files_read']}")
            console.print(f"  Rows added:  {info['rows_added']}")
            console.print(f"  Cache:       {db_path()}")
        return

    result = sync_all()
    session_noun = "session" if result.sessions_added == 1 else "sessions"
    tc_noun = "entry" if result.timeclock_added == 1 else "entries"
    console.print(
        f"[bold green]Synced[/] {result.sessions_added} {session_noun} and "
        f"{result.timeclock_added} timeclock {tc_noun} "
        f"across {result.files_read} file(s)."
    )
    console.print(f"  Cache: [dim]{db_path()}[/]")


@app.command(name="reset")
def db_reset(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete the SQLite cache (cache.db). Safe to re-run sync afterwards."""
    import sys

    from halyard.db import db_path, reset

    path = db_path()
    if not path.exists():
        console.print("[yellow]No cache file found.[/]")
        return

    # Only prompt for an interactive user; scripts / non-TTY callers
    # (and --yes) proceed unprompted so automation is unaffected.
    if not yes and sys.stdin.isatty() and not typer.confirm(f"Delete cache at {path}?"):
        console.print("[yellow]Aborted.[/]")
        return

    reset()
    console.print(f"[bold green]Deleted[/] {path}")
