"""halyard outcome — PR resolution and outcome reporting sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="outcome", help="Resolve AI sessions to PR outcomes.")


@app.command(name="sync")
def outcome_sync(
    since: str | None = typer.Option(None, "--since", help="Start date, e.g. '2026-05-01'."),
    project: str | None = typer.Option(None, "--project", help="Limit to this project slug."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print without writing."),
    force: bool = typer.Option(False, "--force", help="Re-resolve already-resolved sessions."),
) -> None:
    """Scan sessions and resolve each to a PR ref via gh."""
    import dateparser  # type: ignore[import-untyped]

    from halyard.ai_log import find_project_dir, parse_sessions
    from halyard.hub import find_hub
    from halyard.outcomes import gh_available, resolve_sessions

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("[bold red]Error:[/] No Halyard project found.")
        raise typer.Exit(code=1)

    from halyard.outcomes_config import outcomes_enabled

    if not outcomes_enabled(project_dir):
        console.print(
            "[yellow]Outcome collection is disabled in halyard.toml "
            "([outcomes] enabled = false).[/]"
        )
        raise typer.Exit()

    if not gh_available():
        console.print("[yellow]gh not available — skipping PR resolution.[/]")
        console.print("Install gh CLI to enable outcome sync: https://cli.github.com")
        raise typer.Exit()

    since_date = None
    if since:
        parsed = dateparser.parse(since, settings={"RETURN_AS_TIMEZONE_AWARE": False})
        if parsed is None:
            console.print(f"[bold red]Error:[/] Could not parse date '{since}'.")
            raise typer.Exit(code=1)
        since_date = parsed.date()

    sessions = parse_sessions(project_dir)
    results = resolve_sessions(
        project_dir,
        sessions,
        since=since_date,
        project_slug=project,
        force=force,
        dry_run=dry_run,
    )

    if not results:
        console.print("[dim]No sessions to resolve.[/]")
        return

    prefix = "[dim](dry-run)[/] " if dry_run else ""
    for r in results:
        label = r.pr_ref or "no PR"
        console.print(f"{prefix}[cyan]{r.session_hash[:12]}[/] → {label} ([dim]{r.pr_state}[/])")

    synced = len(results)
    console.print(f"\n[green]✓[/] {synced} session{'s' if synced != 1 else ''} processed.")
    if dry_run:
        console.print("[dim]Run without --dry-run to write amendment records.[/]")


@app.command(name="report")
def outcome_report_cmd(
    since: str | None = typer.Option(None, "--since", help="Scan from this date."),
    project: str | None = typer.Option(None, "--project", help="Limit to this project slug."),
) -> None:
    """Display sessions bucketed by outcome (shipped / in-flight / abandoned / no-PR / unsynced)."""
    import dateparser

    from halyard.ai_log import find_project_dir, parse_sessions
    from halyard.hub import find_hub
    from halyard.outcomes import outcome_report

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("[bold red]Error:[/] No Halyard project found.")
        raise typer.Exit(code=1)

    from halyard.outcomes_config import outcomes_enabled

    if not outcomes_enabled(project_dir):
        console.print(
            "[yellow]Outcome collection is disabled in halyard.toml "
            "([outcomes] enabled = false).[/]"
        )
        raise typer.Exit()

    since_date = None
    if since:
        parsed = dateparser.parse(since, settings={"RETURN_AS_TIMEZONE_AWARE": False})
        if parsed is None:
            console.print(f"[bold red]Error:[/] Could not parse date '{since}'.")
            raise typer.Exit(code=1)
        since_date = parsed.date()

    sessions = parse_sessions(project_dir)
    buckets = outcome_report(sessions, since=since_date, project_slug=project)

    period = f"since {since_date}" if since_date else "last 30 days"
    console.print(f"\n[bold]Outcome Report[/] — {period}\n")

    for b in buckets:
        if b.session_count == 0:
            continue
        cost_str = f"${b.total_cost:.2f}" if b.trust else "—"
        trust_tag = f"  [dim]{b.trust}[/]" if b.trust else "  [dim]—[/]"
        plural = "s" if b.session_count != 1 else ""
        console.print(
            f"  {b.label:<30} [bold]{b.session_count:>4}[/] session{plural}  "
            f"[green]{cost_str}[/]{trust_tag}"
        )

    unsynced = next((b for b in buckets if b.label == "Not synced"), None)
    if unsynced and unsynced.session_count > 0:
        console.print("\n[dim]Run [bold]halyard outcome sync[/] to resolve unsynced sessions.[/]")


@app.command(name="attribute")
def outcome_attribute(
    session_id: str = typer.Argument(..., help="12-char session hash (from halyard report)."),
    pr_ref: str = typer.Argument(..., help="PR ref: #42, owner/repo#42, or full GitHub URL."),
) -> None:
    """Manually attribute a session to a PR ref."""
    from halyard.ai_log import find_project_dir
    from halyard.hub import find_hub
    from halyard.outcomes import attribute_session, gh_available

    project_dir = find_project_dir() or find_hub()
    if project_dir is None:
        console.print("[bold red]Error:[/] No Halyard project found.")
        raise typer.Exit(code=1)

    ok, message = attribute_session(project_dir, session_id, pr_ref)
    if ok:
        console.print(f"[green]✓[/] {message}")
        if not gh_available():
            console.print(
                "[dim]gh not available — pr_state set to 'open'. "
                "Run [bold]halyard outcome sync --force[/] to update.[/]"
            )
    else:
        console.print(f"[bold red]Error:[/] {message}")
        raise typer.Exit(code=1)
